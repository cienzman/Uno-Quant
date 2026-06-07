import os
from google import genai
from dotenv import load_dotenv

load_dotenv(".env")
client = genai.Client()

for m in client.models.list():
    if "gemini-2" in m.name:
        print(m.name, m.supported_actions)
