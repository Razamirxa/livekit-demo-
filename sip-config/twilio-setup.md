# Twilio SIP Trunk Setup for Self-Hosted LiveKit

This guide walks you through setting up a Twilio SIP trunk to connect phone calls to your LiveKit voice agent.

## Prerequisites

1. **Twilio Account** - Sign up at [twilio.com](https://www.twilio.com)
2. **Docker services running** (LiveKit Server, SIP, Redis)
3. **Public IP or Domain** - Your server must be accessible from the internet
4. **Port forwarding** - Ports 5060 (SIP) and 10000-10100 (RTP) must be open

## Step 1: Get Your Public IP

Your SIP server needs a public IP address. You can find it by visiting:
- https://whatismyip.com
- Or run: `curl ifconfig.me`

**Note:** If you're behind NAT, you'll need to set up port forwarding on your router.

## Step 2: Twilio Console Setup

### 2.1 Create a SIP Trunk

1. Go to [Twilio Console](https://console.twilio.com)
2. Navigate to **Elastic SIP Trunking** → **Trunks**
3. Click **Create new SIP Trunk**
4. Name it: `LiveKit-Voice-Agent`

### 2.2 Configure Origination (Inbound calls TO your server)

1. In your trunk, go to **Origination**
2. Add a new **Origination URI**:
   ```
   sip:<YOUR_PUBLIC_IP>:5060;transport=udp
   ```
   Example: `sip:203.0.113.50:5060;transport=udp`

3. Set **Priority**: 10
4. Set **Weight**: 10

### 2.3 Configure Termination (Outbound calls FROM your server)

1. Go to **Termination** tab
2. Set **Termination SIP URI**: `your-trunk-name.pstn.twilio.com`
3. Enable **Credential Lists** for authentication:
   - Create a new credential list
   - Add username/password (you'll use these in your SIP trunk config)

### 2.4 Configure Authentication (Recommended)

1. Go to **Authentication** → **IP Access Control Lists**
2. Create a new ACL
3. Add your server's public IP address
4. Apply the ACL to your trunk

### 2.5 Buy a Phone Number

1. Go to **Phone Numbers** → **Buy a Number**
2. Choose a number with Voice capability
3. After purchase, configure the number:
   - **Voice Configuration**: SIP Trunk
   - **SIP Trunk**: Select your `LiveKit-Voice-Agent` trunk

## Step 3: Update Docker Configuration

Update your `.env` file in the `sip-config` folder:

```env
# Twilio Configuration
TWILIO_PHONE_NUMBER=+1234567890
TWILIO_SIP_DOMAIN=your-trunk-name.pstn.twilio.com
TWILIO_SIP_USERNAME=your-username
TWILIO_SIP_PASSWORD=your-password

# Your Public IP
PUBLIC_IP=YOUR_PUBLIC_IP_HERE
```

## Step 4: Create SIP Trunk in LiveKit

Use the LiveKit CLI or API to create a SIP Trunk and Dispatch Rule.

### Install LiveKit CLI

```bash
# Windows (PowerShell)
winget install livekit.livekit-cli

# Or download from: https://github.com/livekit/livekit-cli/releases
```

### Create SIP Trunk (Inbound)

Create a file `inbound-trunk.json`:

```json
{
    "trunk": {
        "name": "Twilio Inbound",
        "inbound_addresses": [],
        "inbound_numbers": ["+1234567890"],
        "inbound_username": "",
        "inbound_password": ""
    }
}
```

**Note:** Leave `inbound_addresses` empty to accept calls from any IP (Twilio's IPs are dynamic).

### Create SIP Trunk (Outbound)

Create a file `outbound-trunk.json`:

```json
{
    "trunk": {
        "name": "Twilio Outbound",
        "outbound_number": "+1234567890",
        "outbound_address": "your-trunk-name.pstn.twilio.com",
        "outbound_username": "your-username",
        "outbound_password": "your-password"
    }
}
```

### Create Dispatch Rule

Create a file `dispatch-rule.json`:

```json
{
    "rule": {
        "dispatchRuleDirect": {
            "roomName": "voice-agent-room"
        }
    },
    "trunk_ids": []
}
```

### Apply Configuration with CLI (lk.exe)

Download `lk.exe` from: https://github.com/livekit/livekit-cli/releases

```powershell
# Set environment variables
$env:LIVEKIT_URL = "http://localhost:7880"
$env:LIVEKIT_API_KEY = "APIKey"
$env:LIVEKIT_API_SECRET = "secretsecretsecretsecret"

# Create inbound trunk (replace +1234567890 with your Twilio number)
.\lk.exe sip inbound create --name "Twilio Inbound" --numbers "+1234567890"

# Create outbound trunk (replace with your Twilio SIP domain)
.\lk.exe sip outbound create --name "Twilio Outbound" --address "your-trunk.pstn.twilio.com" --numbers "+1234567890"

# Create dispatch rule (routes calls to rooms prefixed with "call-")
# Replace ST_xxx with your inbound trunk ID from the previous command
.\lk.exe sip dispatch create --name "Voice Agent Dispatch" --caller "call-" --trunks "ST_xxx"

# List trunks to verify
.\lk.exe sip inbound list
.\lk.exe sip outbound list

# List dispatch rules
.\lk.exe sip dispatch list
```

## Step 5: Port Forwarding (If behind NAT)

Forward these ports on your router to your computer:

| Protocol | External Port | Internal Port | Description |
|----------|--------------|---------------|-------------|
| UDP      | 5060         | 5060          | SIP Signaling |
| TCP      | 5060         | 5060          | SIP Signaling |
| UDP      | 10000-10100  | 10000-10100   | RTP Media |

## Step 6: Update Agent to Connect to Self-Hosted LiveKit

Update your agent's `.env` file:

```env
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=APIKey
LIVEKIT_API_SECRET=secretsecretsecretsecret
```

## Step 7: Test the Setup

1. Start your Docker services:
   ```bash
   cd sip-config
   docker compose up -d
   ```

2. Start your voice agent:
   ```bash
   cd ..
   python agent.py dev
   ```

3. Call your Twilio phone number!

## Troubleshooting

### SIP Container Keeps Restarting
```bash
docker logs sip-config-livekit-sip-1
```

### Check if ports are accessible
```bash
# From another machine or use online port checker
nc -zvu YOUR_PUBLIC_IP 5060
```

### Twilio Call Debugging
1. Go to Twilio Console → **Monitor** → **Logs** → **Calls**
2. Check the SIP response codes

### Common Issues

| Issue | Solution |
|-------|----------|
| 403 Forbidden | Check IP ACL in Twilio |
| 404 Not Found | Verify dispatch rule is created |
| 408 Timeout | Check firewall/port forwarding |
| 503 Service Unavailable | Check SIP container is running |

## Alternative: Use ngrok for Testing

If you can't port forward, you can use ngrok for testing (limited SIP support):

```bash
# Install ngrok
winget install ngrok.ngrok

# Expose SIP port (requires ngrok paid plan for UDP)
ngrok tcp 5060
```

Then use the ngrok address in Twilio's Origination URI.

## Security Recommendations

1. **Use TLS** - Configure SIP TLS on port 5061
2. **Set credentials** - Add username/password to inbound trunk
3. **IP Allowlist** - Only allow Twilio's IP ranges
4. **Monitor logs** - Watch for unauthorized access attempts
