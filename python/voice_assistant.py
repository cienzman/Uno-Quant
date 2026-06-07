import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import voice_state
from voice_tools import TOOLS, handle_answer_microfeedback, handle_query_inventory
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for the AudioWorklet
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

@app.get("/state")
async def get_state():
    return voice_state.get_pending_feedback()

@app.get("/debug")
async def get_debug():
    try:
        with open(os.path.join(os.path.dirname(__file__), "debug_error.txt"), "r") as f:
            return {"log": f.read()}
    except Exception as e:
        return {"log": str(e)}

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

async def dispatch_tool(func_call, context):
    print(f"Tool call received: {func_call.name}")
    try:
        if func_call.name == "answer_microfeedback":
            result = handle_answer_microfeedback(func_call.args, context)
        elif func_call.name == "query_inventory":
            result = handle_query_inventory(func_call.args)
        else:
            result = "Unknown tool."
    except Exception as e:
        import traceback
        result = f"Error executing tool: {e}"
        print(f"Tool execution error: {traceback.format_exc()}")
        with open(os.path.join(os.path.dirname(__file__), "debug_error.txt"), "a") as f:
            f.write(traceback.format_exc() + "\n")
            
    print(f"Tool {func_call.name} returning result: {result}")
    
    return types.FunctionResponse(
        name=func_call.name,
        id=func_call.id,
        response={"result": result}
    )

@app.websocket("/ws/voice")
async def voice_websocket(websocket: WebSocket):
    await websocket.accept()
    
    # Check pending feedback state when connecting
    vstate = voice_state.get_pending_feedback()
    context = {"pending_tag_id": vstate["pending_tag_id"]}
    
    config = types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Puck")
            )
        ),
        tools=[types.Tool(function_declarations=TOOLS)],
        system_instruction=types.Content(parts=[types.Part.from_text(text=(
            "You are a lab inventory assistant. You have access to two tools: "
            "answer_microfeedback and query_inventory. You help users report "
            "remaining quantity of substances. Be concise. "
            "CRITICAL INSTRUCTION: If the user says 'A LOT', 'MEDIUM', 'LOW', or 'SKIP', "
            "you MUST INSTANTLY call the 'answer_microfeedback' tool! "
            "DO NOT just reply with voice! You MUST use the tool immediately so the dashboard updates."
        ))])
    )
    
    try:
        async with client.aio.live.connect(model="gemini-2.5-flash-native-audio-latest", config=config) as session:
            
            # If there's a pending feedback, trigger Gemini to ask immediately
            if vstate["pending_item_name"]:
                initial_prompt = (
                    f"A substance was just returned. You must say EXACTLY this phrase: "
                    f"'Quick check for {vstate['pending_item_name']}. How much {vstate['pending_item_name']} is left?'"
                )
                await session.send(input=initial_prompt, end_of_turn=True)

            async def receive_from_browser():
                try:
                    while True:
                        message = await websocket.receive()
                        if "bytes" in message and message["bytes"]:
                            await session.send(
                                input={"data": message["bytes"], "mime_type": "audio/pcm;rate=16000"},
                            )
                except WebSocketDisconnect:
                    pass
                except Exception:
                    pass

            async def receive_from_gemini():
                try:
                    async for response in session.receive():
                        server_content = getattr(response, "server_content", None)
                        if server_content and server_content.model_turn:
                            for part in server_content.model_turn.parts:
                                if part.inline_data:
                                    await websocket.send_bytes(part.inline_data.data)
                        
                        tool_call = getattr(response, "tool_call", None)
                        if tool_call:
                            print(f"Received tool call from model: {tool_call}")
                            with open("/home/vince/GitHub/ambient-intelligence-internship/python/tool_log.txt", "a") as f:
                                f.write(f"Received tool_call: {tool_call}\n")
                            tool_responses = []
                            for func_call in tool_call.function_calls:
                                resp = await dispatch_tool(func_call, context)
                                tool_responses.append(resp)
                            print("Sending tool responses back to model...")
                            if hasattr(session, "send_tool_response"):
                                await session.send_tool_response(function_responses=tool_responses)
                            else:
                                await session.send(input=tool_responses)
                except Exception as e:
                    print(f"receive_from_gemini error: {e}")
                    import traceback
                    with open(os.path.join(os.path.dirname(__file__), "debug_error.txt"), "a") as f:
                        f.write(f"receive_from_gemini error: {traceback.format_exc()}\n")

            browser_task = asyncio.create_task(receive_from_browser())
            gemini_task = asyncio.create_task(receive_from_gemini())
            
            done, pending = await asyncio.wait(
                [browser_task, gemini_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            for p in pending:
                p.cancel()
            
    except Exception as e:
        print(f"Voice session error: {e}")
        import traceback
        with open(os.path.join(os.path.dirname(__file__), "debug_error.txt"), "a") as f:
            f.write(traceback.format_exc() + "\n")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass

if __name__ == "__main__":
    import uvicorn
    cert_file = "/tmp/vision-agent-cert.pem"
    key_file = "/tmp/vision-agent-key.pem"
    if os.path.exists(cert_file) and os.path.exists(key_file):
        uvicorn.run(app, host="0.0.0.0", port=8502, ssl_keyfile=key_file, ssl_certfile=cert_file)
    else:
        uvicorn.run(app, host="0.0.0.0", port=8502)
