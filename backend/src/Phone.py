"""
Day 6 - Outbound Call Trigger

Dials a SIP participant (your Linphone address) into a LiveKit room.
This creates the room and causes your agent (registered as "my-agent")
to join and run the Day 6 outbound-compliant greeting flow.

Usage:
    python make_call.py
"""

import asyncio
import os
import sys
import uuid

from dotenv import load_dotenv
from livekit import api

load_dotenv(".env.local")
load_dotenv(".env")

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "").strip()
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "").strip()
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "").strip()

# The outbound trunk ID you get back after running:
#   lk sip outbound-trunk create outbound-trunk.json
SIP_TRUNK_ID = os.getenv("SIP_OUTBOUND_TRUNK_ID", "").strip()

# Your Linphone SIP username only (domain is defined in the trunk)
CALLEE_SIP_ADDRESS = "roshan_sankhat"

ROOM_NAME = f"outbound-call-{uuid.uuid4().hex[:8]}"
PARTICIPANT_IDENTITY = "linphone-callee"


async def main():
    missing = [
        name
        for name, val in [
            ("LIVEKIT_URL", LIVEKIT_URL),
            ("LIVEKIT_API_KEY", LIVEKIT_API_KEY),
            ("LIVEKIT_API_SECRET", LIVEKIT_API_SECRET),
            ("SIP_OUTBOUND_TRUNK_ID", SIP_TRUNK_ID),
        ]
        if not val
    ]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}")
        sys.exit(1)

    lkapi = api.LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    )

    try:
        # Step 1: create the room explicitly first.
        print(f"Creating room '{ROOM_NAME}'...")
        await lkapi.room.create_room(
            api.CreateRoomRequest(name=ROOM_NAME)
        )

        # Step 2: explicitly dispatch the agent into that room.
        # Required because the agent is registered with a fixed
        # agent_name ("my-agent"), so it will NOT auto-join rooms
        # unless told to.
        print("Dispatching agent 'my-agent' into the room...")
        await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="my-agent",
                room=ROOM_NAME,
            )
        )

        # Step 3: dial the SIP participant into the same room.
        print(f"Dialing sip:{CALLEE_SIP_ADDRESS} into room '{ROOM_NAME}'...")
        participant = await lkapi.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=SIP_TRUNK_ID,
                sip_call_to=CALLEE_SIP_ADDRESS,
                room_name=ROOM_NAME,
                participant_identity=PARTICIPANT_IDENTITY,
                participant_name="Learner (Linphone)",
                wait_until_answered=True,
            )
        )

        print("Call connected / answered.")
        print(participant)

    except Exception as e:
        print(f"Call failed: {e}")

    finally:
        await lkapi.aclose()


if __name__ == "__main__":
    asyncio.run(main())