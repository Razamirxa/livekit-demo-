from dotenv import load_dotenv
import aiohttp
import os
import json
import wave
import asyncio
from datetime import datetime

from livekit import agents, rtc, api
from livekit.agents import AgentServer, AgentSession, Agent, room_io, RunContext, get_job_context
from livekit.agents.llm import function_tool
from livekit.plugins import noise_cancellation, silero

load_dotenv(".env.local")

# Global variable for conversation recording
conversation_recorder: "ConversationRecorder | None" = None

# Global variables for audio recording
user_audio_recorder: "AudioRecorder | None" = None
agent_audio_recorder: "AudioRecorder | None" = None


class AudioRecorder:
    """Records audio frames to a WAV file at the correct sample rate."""
    
    def __init__(self, filepath: str, num_channels: int = 1):
        self.filepath = filepath
        self.num_channels = num_channels
        self.frames: list[bytes] = []
        self.sample_rate: int | None = None  # Will be set from first frame
        self.is_recording = False
        
    def start(self):
        """Start recording."""
        self.is_recording = True
        self.frames = []
        self.sample_rate = None
        print(f"Audio recording started: {self.filepath}")
        
    def add_frame(self, frame: rtc.AudioFrame):
        """Add an audio frame to the recording."""
        if self.is_recording and frame:
            # Capture sample rate from first frame
            if self.sample_rate is None:
                self.sample_rate = frame.sample_rate
                print(f"  Detected sample rate: {self.sample_rate} Hz for {self.filepath}")
            self.frames.append(bytes(frame.data))
    
    def stop(self):
        """Stop recording and save to WAV file."""
        self.is_recording = False
        
        if not self.frames:
            print(f"No audio frames recorded for {self.filepath}")
            return
        
        if self.sample_rate is None:
            self.sample_rate = 48000  # Default fallback
        
        try:
            # Combine all frames
            audio_data = b''.join(self.frames)
            
            # Write to WAV file
            with wave.open(self.filepath, 'wb') as wav_file:
                wav_file.setnchannels(self.num_channels)
                wav_file.setsampwidth(2)  # 16-bit audio
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(audio_data)
            
            duration = len(audio_data) / (self.sample_rate * self.num_channels * 2)
            print(f"Audio saved: {self.filepath} ({duration:.1f}s, {self.sample_rate}Hz, {len(self.frames)} frames)")
        except Exception as e:
            print(f"Error saving audio recording: {e}")


def combine_audio_files(user_audio_path: str, agent_audio_path: str, output_path: str) -> bool:
    """Combine user and agent audio files into a single WAV file.
    
    This mixes both audio streams together to create a single call recording.
    """
    import struct
    
    try:
        # Read user audio
        with wave.open(user_audio_path, 'rb') as user_wav:
            user_params = user_wav.getparams()
            user_frames = user_wav.readframes(user_params.nframes)
        
        # Read agent audio  
        with wave.open(agent_audio_path, 'rb') as agent_wav:
            agent_params = agent_wav.getparams()
            agent_frames = agent_wav.readframes(agent_params.nframes)
        
        # Use the higher sample rate as target
        target_sample_rate = max(user_params.framerate, agent_params.framerate)
        
        # Convert bytes to samples (16-bit signed integers)
        user_samples = list(struct.unpack(f'<{len(user_frames)//2}h', user_frames))
        agent_samples = list(struct.unpack(f'<{len(agent_frames)//2}h', agent_frames))
        
        # Resample if needed (simple linear interpolation)
        def resample(samples: list, from_rate: int, to_rate: int) -> list:
            if from_rate == to_rate:
                return samples
            ratio = to_rate / from_rate
            new_length = int(len(samples) * ratio)
            resampled = []
            for i in range(new_length):
                src_idx = i / ratio
                idx = int(src_idx)
                if idx >= len(samples) - 1:
                    resampled.append(samples[-1])
                else:
                    frac = src_idx - idx
                    resampled.append(int(samples[idx] * (1 - frac) + samples[idx + 1] * frac))
            return resampled
        
        user_samples = resample(user_samples, user_params.framerate, target_sample_rate)
        agent_samples = resample(agent_samples, agent_params.framerate, target_sample_rate)
        
        # Pad shorter audio with silence
        max_length = max(len(user_samples), len(agent_samples))
        user_samples.extend([0] * (max_length - len(user_samples)))
        agent_samples.extend([0] * (max_length - len(agent_samples)))
        
        # Mix audio (average both channels, with clipping prevention)
        mixed_samples = []
        for u, a in zip(user_samples, agent_samples):
            mixed = (u + a) // 2  # Simple mix
            mixed = max(-32768, min(32767, mixed))  # Clamp to 16-bit range
            mixed_samples.append(mixed)
        
        # Convert back to bytes
        mixed_bytes = struct.pack(f'<{len(mixed_samples)}h', *mixed_samples)
        
        # Write combined file
        with wave.open(output_path, 'wb') as out_wav:
            out_wav.setnchannels(1)
            out_wav.setsampwidth(2)
            out_wav.setframerate(target_sample_rate)
            out_wav.writeframes(mixed_bytes)
        
        duration = len(mixed_samples) / target_sample_rate
        print(f"Combined audio saved: {output_path} ({duration:.1f}s, {target_sample_rate}Hz)")
        return True
        
    except Exception as e:
        print(f"Error combining audio files: {e}")
        return False


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
    global conversation_recorder, user_audio_recorder, agent_audio_recorder
    ctx = get_job_context()
    
    user_audio_path = None
    agent_audio_path = None
    
    # Stop conversation recording
    if conversation_recorder:
        conversation_recorder.stop()
        conversation_recorder = None
    
    # Stop user audio recording
    if user_audio_recorder:
        user_audio_path = user_audio_recorder.filepath
        user_audio_recorder.stop()
        user_audio_recorder = None
    
    # Stop agent audio recording
    if agent_audio_recorder:
        agent_audio_path = agent_audio_recorder.filepath
        agent_audio_recorder.stop()
        agent_audio_recorder = None
    
    # Combine audio files into single call recording
    if user_audio_path and agent_audio_path:
        if os.path.exists(user_audio_path) and os.path.exists(agent_audio_path):
            combined_path = user_audio_path.replace("user_audio_", "call_recording_")
            combine_audio_files(user_audio_path, agent_audio_path, combined_path)
    
    if ctx is None:
        # Not running in a job context (console mode)
        return
    
    # Shutdown the job context which will end the session cleanly
    result = ctx.shutdown()
    if result is not None:
        await result


async def start_recording(room_name: str) -> None:
    """Start recording the conversation.
    
    Recording capabilities:
    - Console mode: Transcript recording only (text-based simulation, no real audio)
    - LiveKit room mode: Transcript + Separate user/agent audio files (saved at native sample rates)
    """
    global conversation_recorder, user_audio_recorder, agent_audio_recorder
    
    # Create recordings directory if it doesn't exist
    recordings_dir = "recordings"
    if not os.path.exists(recordings_dir):
        os.makedirs(recordings_dir)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Always start conversation transcript recording (works in both modes)
    transcript_filepath = f"{recordings_dir}/transcript_{timestamp}.json"
    conversation_recorder = ConversationRecorder(transcript_filepath)
    conversation_recorder.start()
    
    # Check if we're in console mode
    ctx = get_job_context()
    is_console_mode = ctx is None or room_name.startswith("FAKE_")
    
    if is_console_mode:
        # Console mode: only transcript recording (no real audio in console simulation)
        print("Console mode: Transcript recording started. Note: Audio recording requires LiveKit room mode.")
        return
    
    # LiveKit room mode: Start separate audio recordings
    user_audio_filepath = f"{recordings_dir}/user_audio_{timestamp}.wav"
    agent_audio_filepath = f"{recordings_dir}/agent_audio_{timestamp}.wav"
    
    user_audio_recorder = AudioRecorder(user_audio_filepath)
    agent_audio_recorder = AudioRecorder(agent_audio_filepath)
    
    user_audio_recorder.start()
    agent_audio_recorder.start()
    
    print(f"LiveKit room mode: Recording started")
    print(f"  - Transcript: {transcript_filepath}")
    print(f"  - User audio: {user_audio_filepath}")
    print(f"  - Agent audio: {agent_audio_filepath}")


async def stop_recording() -> bool:
    """Stop the active recording and combine audio files."""
    global conversation_recorder, user_audio_recorder, agent_audio_recorder
    
    stopped = False
    user_audio_path = None
    agent_audio_path = None
    
    # Stop conversation recording
    if conversation_recorder:
        conversation_recorder.stop()
        conversation_recorder = None
        stopped = True
    
    # Stop user audio recording
    if user_audio_recorder:
        user_audio_path = user_audio_recorder.filepath
        user_audio_recorder.stop()
        user_audio_recorder = None
        stopped = True
    
    # Stop agent audio recording
    if agent_audio_recorder:
        agent_audio_path = agent_audio_recorder.filepath
        agent_audio_recorder.stop()
        agent_audio_recorder = None
        stopped = True
    
    # Combine audio files into single call recording
    if user_audio_path and agent_audio_path:
        if os.path.exists(user_audio_path) and os.path.exists(agent_audio_path):
            # Generate combined file path
            combined_path = user_audio_path.replace("user_audio_", "call_recording_")
            combine_audio_files(user_audio_path, agent_audio_path, combined_path)
    
    if not stopped:
        print("No active recording to stop")
        
    return stopped


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


@server.rtc_session()
async def my_agent(ctx: agents.JobContext):
    global conversation_recorder, user_audio_recorder, agent_audio_recorder
    
    # Start recording when the call begins
    await start_recording(ctx.room.name)
    
    # Add shutdown callback to stop recording when call ends
    async def stop_recording_on_shutdown():
        await stop_recording()
    
    ctx.add_shutdown_callback(stop_recording_on_shutdown)
    
    # Set up audio frame capture for user audio (from remote participant)
    async def capture_user_audio_frames(stream: rtc.AudioStream):
        """Capture user audio frames from the stream."""
        async for event in stream:
            if user_audio_recorder and user_audio_recorder.is_recording:
                user_audio_recorder.add_frame(event.frame)
    
    # Subscribe to audio tracks from remote participants (user) for recording
    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO and user_audio_recorder:
            audio_stream = rtc.AudioStream(track)
            asyncio.create_task(capture_user_audio_frames(audio_stream))
            print(f"Recording: Capturing USER audio from {participant.identity}")
    
    # Set up audio frame capture for agent audio (from local published track)
    async def capture_agent_audio_frames(stream: rtc.AudioStream):
        """Capture agent audio frames from the stream."""
        async for event in stream:
            if agent_audio_recorder and agent_audio_recorder.is_recording:
                agent_audio_recorder.add_frame(event.frame)
    
    # Subscribe to local audio tracks (agent) for recording
    @ctx.room.on("local_track_published")
    def on_local_track_published(publication: rtc.LocalTrackPublication, track: rtc.Track):
        if track.kind == rtc.TrackKind.KIND_AUDIO and agent_audio_recorder:
            audio_stream = rtc.AudioStream(track)
            asyncio.create_task(capture_agent_audio_frames(audio_stream))
            print(f"Recording: Capturing AGENT audio")
    
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
    )

    await session.generate_reply(
        instructions="Greet the user and offer your assistance."
    )


if __name__ == "__main__":
    agents.cli.run_app(server)
