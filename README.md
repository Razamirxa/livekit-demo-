# LiveKit Voice Agent

A simple voice AI assistant built with LiveKit Agents framework using STT-LLM-TTS pipeline.

## Features

- **Speech-to-Text (STT)**: AssemblyAI Universal-Streaming
- **Language Model (LLM)**: OpenAI GPT-4.1 mini
- **Text-to-Speech (TTS)**: Cartesia Sonic-3
- **Voice Activity Detection (VAD)**: Silero
- **Turn Detection**: Multilingual Model
- **Noise Cancellation**: BVC (for standard participants) and BVCTelephony (for SIP participants)

## Prerequisites

- Python >= 3.9
- LiveKit Cloud account (free tier available at https://cloud.livekit.io/)
- UV package manager (recommended) or pip

## Setup

### 1. Install UV (if not already installed)

```powershell
# Windows
winget install astral-sh.uv
```

Or use pip:
```powershell
pip install uv
```

### 2. Install Dependencies

Using UV:
```powershell
uv pip install -r requirements.txt
```

Or using pip:
```powershell
pip install -r requirements.txt
```

### 3. Configure Environment Variables

1. Sign up for a free LiveKit Cloud account at https://cloud.livekit.io/
2. Create a new project
3. Get your API keys from the project settings
4. Update the `.env.local` file with your credentials:

```env
LIVEKIT_API_KEY=your_api_key_here
LIVEKIT_API_SECRET=your_api_secret_here
LIVEKIT_URL=your_livekit_server_url_here
```

### 4. Download Model Files

Before running the agent, download the required model files:

```powershell
uv run agent.py download-files
```

Or with Python directly:
```powershell
python agent.py download-files
```

## Running the Agent

### Console Mode (Terminal Only)

Run the agent locally in your terminal:

```powershell
uv run agent.py console
```

Or:
```powershell
python agent.py console
```

You can speak to the agent directly in your terminal.

### Development Mode

Run the agent in development mode to connect to LiveKit Cloud:

```powershell
uv run agent.py dev
```

Or:
```powershell
python agent.py dev
```

Then access the Agents Playground at your LiveKit Cloud project to interact with the agent.

### Production Mode

Run the agent in production mode:

```powershell
uv run agent.py start
```

Or:
```powershell
python agent.py start
```

## How It Works

1. The agent connects to a LiveKit room as a participant
2. It listens for audio input from users
3. Speech is converted to text using AssemblyAI
4. Text is processed by GPT-4.1 mini to generate responses
5. Responses are converted to speech using Cartesia Sonic-3
6. Audio is played back to the user in real-time

## Agent Behavior

The assistant is configured with the following personality:
- Helpful and eager to assist
- Provides concise, to-the-point responses
- Avoids complex formatting and emojis
- Curious, friendly, and has a sense of humor

## Customization

To customize the agent's behavior, modify the `instructions` parameter in the `Assistant` class in `agent.py`.

To use different AI models, change the model identifiers in the `AgentSession`:
- `stt`: Speech-to-Text model
- `llm`: Language model
- `tts`: Text-to-Speech model

See the [LiveKit AI Models documentation](https://docs.livekit.io/agents/models/) for available options.

## Deployment

To deploy to LiveKit Cloud:

1. Install LiveKit CLI:
```powershell
winget install LiveKit.LiveKitCLI
```

2. Link your LiveKit Cloud project:
```powershell
lk cloud auth
```

3. Deploy the agent:
```powershell
lk agent create
```

## Resources

- [LiveKit Documentation](https://docs.livekit.io/)
- [LiveKit Agents Quickstart](https://docs.livekit.io/agents/start/voice-ai/)
- [LiveKit GitHub](https://github.com/livekit/agents)
- [LiveKit Slack Community](https://livekit.io/join-slack)

## License

This project follows the LiveKit open source framework under the Apache 2.0 license.
