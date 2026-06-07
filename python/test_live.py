import os
import asyncio
from google import genai
from dotenv import load_dotenv

load_dotenv(".env")
client = genai.Client()

async def main():
    try:
        async with client.aio.live.connect(model="gemini-2.0-flash-exp") as session:
            print("Connected successfully!")
            await session.send(input="Hello?", end_of_turn=True)
            async for response in session.receive():
                print(response)
                break
    except Exception as e:
        print(f"Exception: {type(e).__name__}: {e}")

asyncio.run(main())
