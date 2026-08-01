import os
import json
import tempfile
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from groq import Groq
from duckduckgo_search import DDGS
import edge_tts

import firebase_admin
from firebase_admin import credentials, firestore

app = FastAPI(title="Ultron Core Engine", version="13.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

groq_api_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api_key) if groq_api_key else None

db = None
firebase_json = os.getenv("FIREBASE_CREDENTIALS")
if firebase_json:
    try:
        clean_json = firebase_json.strip()
        cred_dict = json.loads(clean_json)
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("-> Firebase Memory Online.")
    except Exception as e:
        print(f"-> Firebase Init Error: {e}")
        db = None

def get_user_memory():
    if not db: return ""
    try:
        docs = db.collection("ultron_memory").stream()
        return "\n".join([f"- {doc.to_dict().get('fact')}" for doc in docs])
    except:
        return ""

def perform_web_search(query: str) -> str:
    try:
        results_text = ""
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, max_results=3)]
            if results:
                results_text = "\n\nCRITICAL LIVE WEB DATA (USE THIS TO ANSWER):\n"
                for r in results:
                    results_text += f"- {r.get('title', '')}: {r.get('body', '')}\n"
        return results_text
    except Exception:
        return ""

@app.get("/")
def serve_index(): return FileResponse("index.html")

@app.get("/style.css")
def serve_css(): return FileResponse("style.css", media_type="text/css")

@app.get("/app.js")
def serve_js(): return FileResponse("app.js", media_type="application/javascript")

async def send_tts(websocket: WebSocket, text: str):
    print(f"-> Generating Voice Audio for: '{text}'")
    voice = "en-IN-PrabhatNeural"
    communicate = edge_tts.Communicate(text, voice)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_mp3:
        temp_mp3_path = temp_mp3.name
        
    await communicate.save(temp_mp3_path)
    print("-> Voice generated, sending to phone...")
    
    with open(temp_mp3_path, "rb") as mp3_file:
        await websocket.send_bytes(mp3_file.read())
        
    os.remove(temp_mp3_path)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    chat_history = []
    is_awake = False
    print("-> NEW PHONE CONNECTION ACCEPTED")

    try:
        while True:
            try:
                audio_bytes = await websocket.receive_bytes()
                print(f"-> Received audio chunk from phone: {len(audio_bytes)} bytes")
            except WebSocketDisconnect:
                print("-> Phone disconnected.")
                break
                
            if not audio_bytes or len(audio_bytes) < 1000:
                print("-> Audio chunk too small, ignoring.")
                continue

            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
                temp_audio.write(audio_bytes)
                temp_audio_path = temp_audio.name

            print("-> Sending audio to Groq Whisper for transcription...")
            try:
                with open(temp_audio_path, "rb") as audio_file:
                    transcription = groq_client.audio.transcriptions.create(
                        file=(os.path.basename(temp_audio_path), audio_file.read()),
                        model="whisper-large-v3",
                        language="en",
                        response_format="json" 
                    )
                user_text = transcription.text.strip() if hasattr(transcription, 'text') else transcription.get('text', '').strip()
                print(f"-> Transcription Success! User said: '{user_text}'")
            except Exception as e:
                print(f"-> CRITICAL GROQ ERROR: {e}")
                user_text = ""
            finally:
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)

            lowered = user_text.lower().strip()
            ghost_phrases = ["thank you", "thanks for watching", "subtitles by", "amara.org", "you", "bye"]
            if not user_text or len(user_text) < 2 or lowered in ghost_phrases:
                print("-> Detected ghost/background noise, ignoring.")
                continue
                
            await websocket.send_json({"type": "transcript", "text": user_text})

            # --- WAKE / SLEEP LOGIC ---
            if not is_awake:
                if "ultron" in lowered:
                    is_awake = True
                    print("-> WAKING UP ULTRON")
                    await websocket.send_json({"type": "status", "state": "awake"})
                    await send_tts(websocket, "I am listening.")
                continue
            
            if any(cmd in lowered for cmd in ["shut down", "sleep", "go to sleep"]):
                is_awake = False
                print("-> PUTTING ULTRON TO SLEEP")
                await websocket.send_json({"type": "status", "state": "sleep"})
                await send_tts(websocket, "Going offline. Call me if you need me.")
                continue

            # --- CONVERSATION LOGIC ---
            live_search = ""
            if any(k in lowered for k in ["weather", "news", "today", "latest", "score", "price", "who is", "movie"]):
                search_query = user_text
                if "weather" in lowered and "bangalore" not in lowered:
                    search_query += " in Bangalore"
                print(f"-> Performing Web Search for: {search_query}")
                live_search = perform_web_search(search_query)

            memory_context = get_user_memory()

            system_prompt = f"""
            You are Ultron, a highly advanced AI Assistant. Your creator is Saqib.
            STRICT RULES:
            1. Always use the words "Boss".
            2. Speak in the exact language he speaks to you (English, Hindi, or Urdu).
            3. Use the web data provided below to answer real-time questions.
            4. Keep responses direct, friendly, and concise. No formatting.
            
            MEMORY: {memory_context}
            WEB DATA: {live_search}
            """

            messages = [{"role": "system", "content": system_prompt}] + chat_history[-6:] + [{"role": "user", "content": user_text}]

            print("-> Sending conversation to Llama 3 API...")
            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=250
            )

            reply_text = chat_completion.choices[0].message.content.strip()
            print(f"-> Llama 3 Reply: '{reply_text}'")
            chat_history.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": reply_text}])

            await websocket.send_json({"type": "response_text", "text": reply_text})
            
            # Send the AI response audio
            spoken_text = reply_text.replace("Saqib", "Saaqib") 
            await send_tts(websocket, spoken_text)

    except WebSocketDisconnect:
        print("-> Phone disconnected.")
                    
