"""
LiveKit SIP Management Script
Use this to manage SIP trunks and dispatch rules via Python
"""
import os
import json
import asyncio
from livekit import api

# Configuration - Update these values
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "http://localhost:7880")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "APIKey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "secretsecretsecretsecret")


async def list_sip_trunks():
    """List all SIP trunks"""
    lk = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    
    print("\n=== Inbound SIP Trunks ===")
    inbound_trunks = await lk.sip.list_sip_inbound_trunk(api.ListSIPInboundTrunkRequest())
    for trunk in inbound_trunks.items:
        print(f"  ID: {trunk.sip_trunk_id}")
        print(f"  Name: {trunk.name}")
        print(f"  Numbers: {trunk.numbers}")
        print()
    
    print("\n=== Outbound SIP Trunks ===")
    outbound_trunks = await lk.sip.list_sip_outbound_trunk(api.ListSIPOutboundTrunkRequest())
    for trunk in outbound_trunks.items:
        print(f"  ID: {trunk.sip_trunk_id}")
        print(f"  Name: {trunk.name}")
        print(f"  Address: {trunk.address}")
        print(f"  Numbers: {trunk.numbers}")
        print()
    
    await lk.aclose()


async def list_dispatch_rules():
    """List all dispatch rules"""
    lk = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    
    print("\n=== SIP Dispatch Rules ===")
    rules = await lk.sip.list_sip_dispatch_rule(api.ListSIPDispatchRuleRequest())
    for rule in rules.items:
        print(f"  ID: {rule.sip_dispatch_rule_id}")
        print(f"  Name: {rule.name}")
        print(f"  Trunk IDs: {rule.trunk_ids}")
        print(f"  Rule: {rule.rule}")
        print()
    
    await lk.aclose()


async def create_inbound_trunk(name: str, numbers: list[str], allowed_addresses: list[str] = None):
    """Create an inbound SIP trunk"""
    lk = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    
    request = api.CreateSIPInboundTrunkRequest(
        trunk=api.SIPInboundTrunkInfo(
            name=name,
            numbers=numbers,
            allowed_addresses=allowed_addresses or [],
        )
    )
    
    trunk = await lk.sip.create_sip_inbound_trunk(request)
    print(f"Created inbound trunk: {trunk.sip_trunk_id}")
    
    await lk.aclose()
    return trunk


async def create_outbound_trunk(
    name: str, 
    address: str, 
    numbers: list[str],
    auth_username: str = None,
    auth_password: str = None
):
    """Create an outbound SIP trunk"""
    lk = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    
    request = api.CreateSIPOutboundTrunkRequest(
        trunk=api.SIPOutboundTrunkInfo(
            name=name,
            address=address,
            numbers=numbers,
            auth_username=auth_username or "",
            auth_password=auth_password or "",
        )
    )
    
    trunk = await lk.sip.create_sip_outbound_trunk(request)
    print(f"Created outbound trunk: {trunk.sip_trunk_id}")
    
    await lk.aclose()
    return trunk


async def create_dispatch_rule(name: str, room_prefix: str, trunk_ids: list[str] = None):
    """Create a dispatch rule for incoming calls"""
    lk = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    
    request = api.CreateSIPDispatchRuleRequest(
        name=name,
        trunk_ids=trunk_ids or [],
        rule=api.SIPDispatchRule(
            dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                room_prefix=room_prefix,
            )
        )
    )
    
    rule = await lk.sip.create_sip_dispatch_rule(request)
    print(f"Created dispatch rule: {rule.sip_dispatch_rule_id}")
    
    await lk.aclose()
    return rule


async def delete_inbound_trunk(trunk_id: str):
    """Delete an inbound SIP trunk"""
    lk = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    
    await lk.sip.delete_sip_trunk(api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id))
    print(f"Deleted trunk: {trunk_id}")
    
    await lk.aclose()


async def delete_dispatch_rule(rule_id: str):
    """Delete a dispatch rule"""
    lk = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    
    await lk.sip.delete_sip_dispatch_rule(api.DeleteSIPDispatchRuleRequest(sip_dispatch_rule_id=rule_id))
    print(f"Deleted dispatch rule: {rule_id}")
    
    await lk.aclose()


async def setup_twilio_trunk(
    phone_number: str,
    twilio_domain: str,
    twilio_username: str = None,
    twilio_password: str = None
):
    """Complete setup for Twilio SIP trunk"""
    print("Setting up Twilio SIP Trunk...")
    
    # Create inbound trunk
    inbound = await create_inbound_trunk(
        name="Twilio Inbound",
        numbers=[phone_number]
    )
    
    # Create outbound trunk
    outbound = await create_outbound_trunk(
        name="Twilio Outbound",
        address=twilio_domain,
        numbers=[phone_number],
        auth_username=twilio_username,
        auth_password=twilio_password
    )
    
    # Create dispatch rule
    rule = await create_dispatch_rule(
        name="Voice Agent Dispatch",
        room_prefix="call-",
        trunk_ids=[inbound.sip_trunk_id]
    )
    
    print("\n=== Setup Complete ===")
    print(f"Inbound Trunk ID: {inbound.sip_trunk_id}")
    print(f"Outbound Trunk ID: {outbound.sip_trunk_id}")
    print(f"Dispatch Rule ID: {rule.sip_dispatch_rule_id}")
    
    return inbound, outbound, rule


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("""
LiveKit SIP Management Script

Usage:
    python sip_manager.py list           - List all trunks and rules
    python sip_manager.py setup          - Interactive setup for Twilio
    python sip_manager.py delete-all     - Delete all trunks and rules
        """)
        sys.exit(0)
    
    command = sys.argv[1]
    
    if command == "list":
        asyncio.run(list_sip_trunks())
        asyncio.run(list_dispatch_rules())
    
    elif command == "setup":
        print("Twilio SIP Trunk Setup")
        phone = input("Enter your Twilio phone number (e.g., +1234567890): ")
        domain = input("Enter your Twilio SIP domain (e.g., xxx.pstn.twilio.com): ")
        username = input("Enter Twilio username (press Enter to skip): ") or None
        password = input("Enter Twilio password (press Enter to skip): ") or None
        
        asyncio.run(setup_twilio_trunk(phone, domain, username, password))
    
    elif command == "delete-all":
        confirm = input("Are you sure you want to delete all SIP trunks and rules? (yes/no): ")
        if confirm.lower() == "yes":
            asyncio.run(list_sip_trunks())
            # Add deletion logic here
            print("Deletion not implemented - use lk.exe CLI to delete individual items")
    
    else:
        print(f"Unknown command: {command}")
