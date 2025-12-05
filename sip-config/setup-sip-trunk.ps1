# LiveKit SIP Trunk Setup Script for Twilio
# Run this after installing livekit-cli and configuring your JSON files

param(
    [string]$LiveKitUrl = "http://localhost:7880",
    [string]$ApiKey = "APIKey",
    [string]$ApiSecret = "secretsecretsecretsecret"
)

Write-Host "=== LiveKit SIP Trunk Setup ===" -ForegroundColor Cyan

# Set environment variables
$env:LIVEKIT_URL = $LiveKitUrl
$env:LIVEKIT_API_KEY = $ApiKey
$env:LIVEKIT_API_SECRET = $ApiSecret

Write-Host "`nUsing LiveKit Server: $LiveKitUrl" -ForegroundColor Yellow
Write-Host "API Key: $ApiKey" -ForegroundColor Yellow

# Check if livekit-cli is installed
$cliExists = Get-Command livekit-cli -ErrorAction SilentlyContinue
if (-not $cliExists) {
    Write-Host "`n[!] livekit-cli not found. Installing..." -ForegroundColor Red
    Write-Host "Run: winget install livekit.livekit-cli" -ForegroundColor Yellow
    Write-Host "Or download from: https://github.com/livekit/livekit-cli/releases" -ForegroundColor Yellow
    exit 1
}

Write-Host "`n[✓] livekit-cli found" -ForegroundColor Green

# Create Inbound Trunk
Write-Host "`n[1/3] Creating Inbound SIP Trunk..." -ForegroundColor Cyan
if (Test-Path "inbound-trunk.json") {
    try {
        livekit-cli sip trunk create --request inbound-trunk.json
        Write-Host "[✓] Inbound trunk created" -ForegroundColor Green
    } catch {
        Write-Host "[!] Failed to create inbound trunk: $_" -ForegroundColor Red
    }
} else {
    Write-Host "[!] inbound-trunk.json not found" -ForegroundColor Red
}

# Create Outbound Trunk
Write-Host "`n[2/3] Creating Outbound SIP Trunk..." -ForegroundColor Cyan
if (Test-Path "outbound-trunk.json") {
    try {
        livekit-cli sip trunk create --request outbound-trunk.json
        Write-Host "[✓] Outbound trunk created" -ForegroundColor Green
    } catch {
        Write-Host "[!] Failed to create outbound trunk: $_" -ForegroundColor Red
    }
} else {
    Write-Host "[!] outbound-trunk.json not found" -ForegroundColor Red
}

# Create Dispatch Rule
Write-Host "`n[3/3] Creating Dispatch Rule..." -ForegroundColor Cyan
if (Test-Path "dispatch-rule.json") {
    try {
        livekit-cli sip dispatch-rule create --request dispatch-rule.json
        Write-Host "[✓] Dispatch rule created" -ForegroundColor Green
    } catch {
        Write-Host "[!] Failed to create dispatch rule: $_" -ForegroundColor Red
    }
} else {
    Write-Host "[!] dispatch-rule.json not found" -ForegroundColor Red
}

# List created resources
Write-Host "`n=== Created Resources ===" -ForegroundColor Cyan

Write-Host "`nSIP Trunks:" -ForegroundColor Yellow
livekit-cli sip trunk list

Write-Host "`nDispatch Rules:" -ForegroundColor Yellow
livekit-cli sip dispatch-rule list

Write-Host "`n=== Setup Complete ===" -ForegroundColor Green
Write-Host @"

Next Steps:
1. Update inbound-trunk.json with your Twilio phone number
2. Update outbound-trunk.json with your Twilio credentials
3. Re-run this script to update the trunks
4. Configure Twilio to point to your server's public IP

See twilio-setup.md for detailed instructions.
"@
