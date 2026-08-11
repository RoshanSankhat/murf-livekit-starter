import asyncio, os
from dotenv import load_dotenv
from livekit import api

load_dotenv(".env.local")
load_dotenv(".env")

async def main():
    lkapi = api.LiveKitAPI(
        url=os.getenv("LIVEKIT_URL"),
        api_key=os.getenv("LIVEKIT_API_KEY"),
        api_secret=os.getenv("LIVEKIT_API_SECRET"),
    )
    await lkapi.room.delete_room(api.DeleteRoomRequest(room="outbound-call-82176557"))
    print("Room deleted — call force-ended.")
    await lkapi.aclose()

asyncio.run(main())