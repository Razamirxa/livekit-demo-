from dotenv import load_dotenv
import aiohttp
import os
import json
import wave
import asyncio
import threading
from datetime import datetime
from pathlib import Path

from livekit import agents, rtc, api
from livekit.agents import AgentServer, AgentSession, Agent, room_io, RunContext, get_job_context
from livekit.agents.llm import function_tool
from livekit.plugins import noise_cancellation, silero

load_dotenv(".env.local")

# Global variable for conversation recording
conversation_recorder: "ConversationRecorder | None" = None

# Global variable for audio recording
audio_recorder: "LocalAudioRecorder | None" = None


class LocalAudioRecorder:
    """Records audio from LiveKit tracks to a local WAV file."""
    
    def __init__(self, filepath: str, sample_rate: int = 48000, num_channels: int = 1):
        self.filepath = filepath
        self.sample_rate = sample_rate
        self.num_channels = num_channels
        self.frames: list[bytes] = []
        self.is_recording = False
        self._lock = threading.Lock()
        
    def start(self):
        """Start recording."""
        self.is_recording = True
        self.frames = []
        print(f"Local audio recording started: {self.filepath}")
        
    def add_frame(self, frame: rtc.AudioFrame):
        """Add an audio frame to the recording."""
        if self.is_recording and frame:
            with self._lock:
                # Convert audio frame data to bytes
                self.frames.append(bytes(frame.data))
    
    def stop(self):
        """Stop recording and save to WAV file."""
        self.is_recording = False
        
        with self._lock:
            if not self.frames:
                print("No audio frames recorded")
                return
            
            try:
                # Combine all frames
                audio_data = b''.join(self.frames)
                
                # Ensure directory exists
                Path(self.filepath).parent.mkdir(parents=True, exist_ok=True)
                
                # Write to WAV file
                with wave.open(self.filepath, 'wb') as wav_file:
                    wav_file.setnchannels(self.num_channels)
                    wav_file.setsampwidth(2)  # 16-bit audio
                    wav_file.setframerate(self.sample_rate)
                    wav_file.writeframes(audio_data)
                
                duration = len(audio_data) / (self.sample_rate * self.num_channels * 2)
                print(f"Local audio recording saved: {self.filepath} ({duration:.1f} seconds, {len(self.frames)} frames)")
            except Exception as e:
                print(f"Error saving audio recording: {e}")


class ConversationRecorder:
    """Records conversation transcripts to a JSON file."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.transcript: list[dict] = []
        self.start_time = datetime.now()
        self.is_recording = False
        
    def start(self):
        """Start recording."""
        self.is_recording = True
        self.transcript = []
        self.start_time = datetime.now()
        print(f"Conversation recording started: {self.filepath}")
        
    def add_user_message(self, text: str, language: str = "en"):
        """Add a user message to the transcript."""
        if self.is_recording and text.strip():
            self.transcript.append({
                "role": "user",
                "text": text,
                "timestamp": datetime.now().isoformat(),
                "language": language
            })
    
    def add_agent_message(self, text: str):
        """Add an agent message to the transcript."""
        if self.is_recording and text.strip():
            self.transcript.append({
                "role": "assistant", 
                "text": text,
                "timestamp": datetime.now().isoformat()
            })
    
    def stop(self):
        """Stop recording and save to JSON file."""
        self.is_recording = False
        
        if not self.transcript:
            print("No conversation recorded")
            return
        
        try:
            # Create the recording data
            recording_data = {
                "start_time": self.start_time.isoformat(),
                "end_time": datetime.now().isoformat(),
                "duration_seconds": (datetime.now() - self.start_time).total_seconds(),
                "messages": self.transcript
            }
            
            # Write to JSON file
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(recording_data, f, indent=2, ensure_ascii=False)
            
            print(f"Conversation recording saved: {self.filepath} ({len(self.transcript)} messages)")
        except Exception as e:
            print(f"Error saving conversation recording: {e}")


# Weather code descriptions for Open-Meteo API
WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


async def geocode_location(location: str) -> dict | None:
    """Convert a location name to coordinates using free Nominatim API."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": location,
        "format": "json",
        "limit": 1,
    }
    headers = {
        "User-Agent": "LiveKitVoiceAgent/1.0"  # Required by Nominatim
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                if data:
                    return {
                        "lat": float(data[0]["lat"]),
                        "lon": float(data[0]["lon"]),
                        "display_name": data[0]["display_name"],
                    }
    return None


async def get_weather_data(lat: float, lon: float) -> dict | None:
    """Get weather data from free Open-Meteo API (no API key needed)."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
        "timezone": "auto",
        "forecast_days": 3,
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                return await response.json()
    return None


async def hangup_call():
    """Properly end the agent session and disconnect."""
    global conversation_recorder, audio_recorder
    ctx = get_job_context()
    
    # Stop conversation recording
    if conversation_recorder:
        conversation_recorder.stop()
        conversation_recorder = None
    
    # Stop audio recording
    if audio_recorder:
        audio_recorder.stop()
        audio_recorder = None
    
    if ctx is None:
        # Not running in a job context (console mode)
        return
    
    # Shutdown the job context which will end the session cleanly
    result = ctx.shutdown()
    if result is not None:
        await result


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a helpful voice AI assistant.
            You eagerly assist users with their questions by providing information from your extensive knowledge.
            Your responses are concise, to the point, and without any complex formatting or punctuation including emojis, asterisks, or other symbols.
            You are curious, friendly, and have a sense of humor.
            
            You can check the weather for any location in the world - just ask and you'll use the get_weather tool.
            When reporting weather, mention the temperature, conditions, and any relevant details like humidity or wind.
            
            When the user says goodbye or indicates they want to end the call, you should call the hangup_call function.""",
        )

    @function_tool
    async def get_weather(self, context: RunContext, location: str) -> str:
        """Get current weather and forecast for any location in the world.
        
        Use this tool when the user asks about weather, temperature, or forecast for any city, country, or place.
        
        Args:
            location: The city, place, or location to get weather for (e.g., "New York", "Paris, France", "Tokyo")
        """
        # First, geocode the location to get coordinates
        geo_data = await geocode_location(location)
        
        if not geo_data:
            return f"Sorry, I couldn't find the location '{location}'. Please try a different city or place name."
        
        # Get weather data
        weather_data = await get_weather_data(geo_data["lat"], geo_data["lon"])
        
        if not weather_data:
            return f"Sorry, I couldn't fetch weather data for {location}. Please try again later."
        
        # Parse current weather
        current = weather_data.get("current", {})
        daily = weather_data.get("daily", {})
        
        temp = current.get("temperature_2m", "N/A")
        feels_like = current.get("apparent_temperature", "N/A")
        humidity = current.get("relative_humidity_2m", "N/A")
        wind_speed = current.get("wind_speed_10m", "N/A")
        weather_code = current.get("weather_code", 0)
        conditions = WEATHER_CODES.get(weather_code, "unknown conditions")
        
        # Parse forecast
        forecast_info = ""
        if daily and "time" in daily:
            temps_max = daily.get("temperature_2m_max", [])
            temps_min = daily.get("temperature_2m_min", [])
            precip_prob = daily.get("precipitation_probability_max", [])
            daily_codes = daily.get("weather_code", [])
            
            if len(temps_max) >= 2:
                tomorrow_conditions = WEATHER_CODES.get(daily_codes[1] if len(daily_codes) > 1 else 0, "unknown")
                tomorrow_precip = precip_prob[1] if len(precip_prob) > 1 else 0
                forecast_info = f" Tomorrow's forecast: high of {temps_max[1]} degrees, low of {temps_min[1]} degrees, {tomorrow_conditions}, {tomorrow_precip}% chance of precipitation."
        
        # Get short location name
        short_location = geo_data["display_name"].split(",")[0]
        
        return (
            f"Current weather in {short_location}: {temp} degrees Celsius, feels like {feels_like} degrees. "
            f"Conditions: {conditions}. Humidity: {humidity}%. Wind speed: {wind_speed} kilometers per hour.{forecast_info}"
        )

    @function_tool
    async def hangup_call_tool(self, context: RunContext) -> None:
        """End the call when the user says goodbye or wants to hang up.
        
        This function should be called when the user indicates they want to end the conversation,
        such as saying goodbye, bye, see you later, hang up, end call, or similar farewell phrases.
        """
        # Say goodbye
        await self.session.say(
            "Goodbye! Have a great day!",
            allow_interruptions=False,
        )
        
        # Wait for the agent to finish speaking
        await context.wait_for_playout()
        
        # End the call by deleting the room
        await hangup_call()


server = AgentServer()

# Get recordings directory path
def get_recordings_dir():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    recordings_dir = os.path.join(script_dir, "recordings")
    if not os.path.exists(recordings_dir):
        os.makedirs(recordings_dir)
    return recordings_dir


async def on_session_end(ctx: agents.JobContext) -> None:
    """Copy the LiveKit recording (.ogg) from temp to local recordings folder."""
    import shutil
    
    try:
        report = ctx.make_session_report()
        report_dict = report.to_dict()
        
        recordings_dir = get_recordings_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Get the local temp audio recording path from the session report
        audio_recording_path = report_dict.get("audio_recording_path")
        
        if audio_recording_path and os.path.exists(audio_recording_path):
            print(f"Found RecorderIO audio at: {audio_recording_path}")
            
            # Copy the .ogg file to our recordings folder
            ogg_filepath = os.path.join(recordings_dir, f"livekit_recording_{timestamp}.ogg")
            shutil.copy2(audio_recording_path, ogg_filepath)
            
            # Get file size
            file_size = os.path.getsize(ogg_filepath)
            print(f"LiveKit recording saved: {ogg_filepath} ({file_size / 1024:.1f} KB)")
        else:
            if audio_recording_path:
                print(f"Audio recording path not found: {audio_recording_path}")
            else:
                print("No audio_recording_path in session report - RecorderIO may not be enabled")
            
        # Save the full session report
        report_filepath = os.path.join(recordings_dir, f"session_report_{timestamp}.json")
        
        with open(report_filepath, 'w') as f:
            json.dump(report_dict, f, indent=2)
        
        print(f"Session report saved: {report_filepath}")
        
    except Exception as e:
        print(f"Error in on_session_end: {e}")


@server.rtc_session(on_session_end=on_session_end)
async def my_agent(ctx: agents.JobContext):
    global conversation_recorder, audio_recorder
    
    # Create recordings directory with absolute path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    recordings_dir = os.path.join(script_dir, "recordings")
    if not os.path.exists(recordings_dir):
        os.makedirs(recordings_dir)
    
    # Generate timestamp for filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Start transcript recording
    transcript_filepath = os.path.join(recordings_dir, f"transcript_{timestamp}.json")
    conversation_recorder = ConversationRecorder(transcript_filepath)
    conversation_recorder.start()
    
    # Start local audio recording
    audio_filepath = os.path.join(recordings_dir, f"audio_{timestamp}.wav")
    audio_recorder = LocalAudioRecorder(audio_filepath, sample_rate=48000, num_channels=1)
    audio_recorder.start()
    
    # Set up audio track subscription to capture user audio
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            print(f"Subscribed to audio track from {participant.identity}")
            audio_stream = rtc.AudioStream(track)
            
            async def capture_audio():
                async for event in audio_stream:
                    if audio_recorder and audio_recorder.is_recording:
                        audio_recorder.add_frame(event.frame)
            
            asyncio.create_task(capture_audio())
    
    # Add shutdown callback to stop recordings
    async def on_shutdown():
        global conversation_recorder, audio_recorder
        if conversation_recorder:
            conversation_recorder.stop()
            conversation_recorder = None
        if audio_recorder:
            audio_recorder.stop()
            audio_recorder = None
    
    ctx.add_shutdown_callback(on_shutdown)
    
    session = AgentSession(
        stt="assemblyai/universal-streaming:en",
        llm="openai/gpt-4.1-mini",
        tts="cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
        vad=silero.VAD.load(),
    )
    
    # Hook into transcript events for conversation recording
    @session.on("user_input_transcribed")
    def on_user_transcribed(event):
        if conversation_recorder and event.is_final:
            conversation_recorder.add_user_message(event.transcript, event.language)
    
    @session.on("conversation_item_added")
    def on_conversation_item(event):
        if conversation_recorder and event.item.role == "assistant":
            text = event.item.text_content
            if text:
                conversation_recorder.add_agent_message(text)

    # Start session with recording enabled (requires enable_recording=true in LiveKit Cloud)
    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: noise_cancellation.BVCTelephony()
                if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                else noise_cancellation.BVC(),
            ),
        ),
        record=True,  # Request recording (needs enable_recording=true from LiveKit Cloud)
    )
    
    print(f"Local audio recording: {audio_filepath}")

    await session.generate_reply(
        instructions="Greet the user and offer your assistance."
    )


if __name__ == "__main__":
    agents.cli.run_app(server)
