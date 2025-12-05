# Self-Hosted LiveKit SIP Setup Guide

## 📋 Overview

This guide helps you set up LiveKit with SIP support to receive and make phone calls with your voice agent.

## 🏗️ Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Phone Call     │────▶│   SIP Provider   │────▶│  LiveKit SIP     │
│   (PSTN/Mobile)  │     │  (Twilio/Telnyx) │     │   Service        │
└──────────────────┘     └──────────────────┘     └────────┬─────────┘
                                                           │
                                                           ▼
                                                 ┌──────────────────┐
                                                 │  LiveKit Server  │
                                                 └────────┬─────────┘
                                                           │
                                                           ▼
                                                 ┌──────────────────┐
                                                 │   Your Agent     │
                                                 │   (agent.py)     │
                                                 └──────────────────┘
```

## 🚀 Quick Start

### Step 1: Prerequisites

- Docker and Docker Compose installed
- A SIP trunk provider account (Twilio or Telnyx recommended)
- A phone number from your provider
- A server with public IP (for production)

### Step 2: Start Services

```bash
cd sip-config
docker-compose up -d
```

### Step 3: Configure SIP Trunk Provider

#### Option A: Twilio Setup

1. **Create SIP Domain** in Twilio Console:
   - Go to: Voice → SIP Domains
   - Click "Create new SIP Domain"
   - Domain name: `your-agent.sip.twilio.com`

2. **Configure Voice URL**:
   - Set the Voice Configuration URL to your LiveKit SIP server
   - Format: `sip:YOUR_SERVER_IP:5060`

3. **Get a Phone Number**:
   - Buy a phone number in Twilio
   - Configure it to route to your SIP Domain

4. **Update Credentials**:
   - Copy your Account SID and Auth Token
   - Update `sip-trunk.yaml` with your credentials

#### Option B: Telnyx Setup

1. **Create SIP Connection**:
   - Go to: SIP Connections → Add Connection
   - Choose "IP Authentication" or "Credentials"
   - Add your server IP

2. **Buy Phone Number**:
   - Purchase a number
   - Assign to your SIP connection

3. **Update Credentials**:
   - Update `sip-trunk.yaml` with Telnyx credentials

### Step 4: Register SIP Trunk with LiveKit

Use the LiveKit CLI to register your trunk:

```bash
# Install LiveKit CLI
pip install livekit-cli

# Create inbound trunk
lk sip trunk create \
  --name "my-trunk" \
  --inbound-addresses "54.172.60.0/30" \
  --api-key devkey \
  --api-secret secret \
  --url http://localhost:7880

# Create dispatch rule
lk sip dispatch-rule create \
  --name "to-agent" \
  --trunk-ids "trunk_id_from_above" \
  --room-name "voice-agent-room" \
  --api-key devkey \
  --api-secret secret \
  --url http://localhost:7880
```

### Step 5: Update Your Agent

Your agent already supports SIP! The noise cancellation in your `agent.py` automatically detects SIP calls:

```python
noise_cancellation=lambda params: noise_cancellation.BVCTelephony()
if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
else noise_cancellation.BVC(),
```

### Step 6: Test

1. Start your agent:
   ```bash
   cd ..
   uv run agent.py start
   ```

2. Call your phone number!

## 📞 Making Outbound Calls

To have your agent make outbound calls, use the LiveKit API:

```python
from livekit import api

async def make_outbound_call(phone_number: str, room_name: str):
    lk_api = api.LiveKitAPI()
    
    # Create SIP participant (makes the call)
    participant = await lk_api.sip.create_sip_participant(
        api.CreateSIPParticipantRequest(
            sip_trunk_id="your-outbound-trunk-id",
            sip_call_to=f"sip:{phone_number}@your-trunk-domain",
            room_name=room_name,
            participant_identity="phone-user",
        )
    )
    
    return participant
```

## 🔧 Configuration Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Docker services (LiveKit, SIP, Redis) |
| `livekit.yaml` | LiveKit server configuration |
| `sip.yaml` | SIP service configuration |
| `sip-trunk.yaml` | SIP trunk and dispatch rules |
| `.env.example` | Environment variables template |

## 🌐 Production Deployment

For production:

1. **Use a proper domain** with SSL certificates
2. **Configure firewall** to allow:
   - UDP 5060 (SIP)
   - TCP 5060 (SIP)
   - TCP 5061 (SIP TLS)
   - UDP 10000-10100 (RTP media)
3. **Use secrets management** for credentials
4. **Enable TLS** for SIP connections
5. **Set up monitoring** for call quality

## 🐛 Troubleshooting

### Calls not connecting
- Check firewall rules
- Verify SIP trunk credentials
- Check LiveKit SIP service logs: `docker-compose logs livekit-sip`

### Audio issues
- Ensure RTP port range is open
- Check codec compatibility
- Verify network connectivity

### Agent not responding
- Ensure agent is running and connected to the room
- Check room name matches dispatch rule
- Verify LiveKit server connectivity

## 📚 Resources

- [LiveKit SIP Documentation](https://docs.livekit.io/sip/)
- [Twilio SIP Trunking](https://www.twilio.com/docs/sip-trunking)
- [Telnyx SIP](https://developers.telnyx.com/docs/v2/sip-trunking)
