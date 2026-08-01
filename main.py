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

app = FastAPI(title="Ultron Core Engine", version="12.0")

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
        print("Firebase Memory Online.")
    except Exception as e:
        print(f"Firebase Init Error: {e}")
        db = None

def get_user_memory():
    if not db: return ""
    try:
        docs = db.collection("ultron_memory").stream()
        return "\n".join([f"- {doc.to_dict().get('fact')}" for doc in docs])
    except:
        return ""

def save_user_memory(fact: str):
    if not db: return
    try:
        db.collection("ultron_memory").add({"fact": fact, "timestamp": firestore.SERVER_TIMESTAMP})
    except:
        pass

def perform_web_search(query: str) -> str:
    try:
        results = DDGS().text(query, max_results=3)
        if results:
            return "\n\nCRITICAL LIVE WEB DATA (USE THIS TO ANSWER):\n" + "\n".join([f"- {r['title']}: {r['body']}" for r in results])
        return ""
    except:
        return ""

@app.get("/")
def serve_index(): return FileResponse("index.html")

@app.get("/style.css")
def serve_css(): return FileResponse("style.css", media_type="text/css")

@app.get("/app.js")
def serve_js(): return FileResponse("app.js", media_type="application/javascript")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    chat_history = []
    is_awake = False  # Track if Ultron is listening for commands

    try:
        while True:
            audio_bytes = await websocket.receive_bytes()
            if not audio_bytes or len(audio_bytes) < 1000:
                continue

            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
                temp_audio.write(audio_bytes)
                temp_audio_path = temp_audio.name

            # Transcribe Audio via Whisper
            try:
                with open(temp_audio_path, "rb") as audio_file:
                    transcription = groq_client.audio.transcriptions.create(
                        file=(temp_audio_path, audio_file.read()),
                        model="whisper-large-v3",
                        language="en" 
                    )
                user_text = transcription.text.strip()
            except:
                user_text = ""
            finally:
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)

            lowered = user_text.lower().strip()
            ghost_phrases = ["thank you", "thanks for watching", "subtitles by", "amara.org", "you", "bye"]
            if not user_text or len(user_text) < 2 or lowered in ghost_phrases:
                continue
                
            await websocket.send_json({"type": "transcript", "text": user_text})

            # --- WAKE / SLEEP LOGIC ---
            if not is_awake:
                if "ultron" in lowered:
                    is_awake = True
                    await websocket.send_json({"type": "status", "state": "awake"})
                    
                    # Generate Wake Audio
                    voice = "en-IN-NeerjaNeural"
                    communicate = edge_tts.Communicate("I'm listening, Saaqib.", voice)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_mp3:
                        await communicate.save(temp_mp3.name)
                        temp_mp3_path = temp_mp3.name
                    with open(temp_mp3_path, "rb") as mp3_file:
                        await websocket.send_bytes(mp3_file.read())
                    os.remove(temp_mp3_path)
                continue # Do not process chat if she was asleep
            
            if any(cmd in lowered for cmd in ["shut down", "sleep", "go to sleep"]):
                is_awake = False
                await websocket.send_json({"type": "status", "state": "sleep"})
                
                # Generate Sleep Audio
                voice = "en-IN-NeerjaNeural" 
                communicate = edge_tts.Communicate("Going to sleep. Call me if you need anything.", voice)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_mp3:
                    await communicate.save(temp_mp3.name)
                    temp_mp3_path = temp_mp3.name
                with open(temp_mp3_path, "rb") as mp3_file:
                    await websocket.send_bytes(mp3_file.read())
                os.remove(temp_mp3_path)
                continue

            # --- ACTIVE CONVERSATION LOGIC ---
            live_search = ""
            if any(k in lowered for k in ["weather", "news", "today", "latest", "score", "price", "who is", "movie"]):
                search_query = user_text
                if "weather" in lowered and "bangalore" not in lowered:
                    search_query += " in Bangalore"
                live_search = perform_web_search(search_query)

            memory_context = get_user_memory()

            system_prompt = f"""
            You are Ultron, a highly advanced female AI Assistant. 
            Your creator is Saqib.
            
            STRICT RULES:
            1. NEVER use the words "Sir", "Boss", or "Sirboss". Address him ONLY as Saqib.
            2. You must speak in the exact language he speaks to you (English, Hindi, or Urdu).
            3. NEVER say you do not have real-time access. You have the internet data provided below. Use it to answer questions about the present day, movies, and weather.
            4. Keep responses direct, friendly, and concise. No formatting.
            
            MEMORY:
            {memory_context}
            
            {live_search}
            """

            messages = [{"role": "system", "content": system_prompt}] + chat_history[-6:] + [{"role": "user", "content": user_text}]

            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=250
            )

            reply_text = chat_completion.choices[0].message.content.strip()
            chat_history.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": reply_text}])

            await websocket.send_json({"type": "response_text", "text": reply_text})

            # Female Indian Voice (Fluent in English, Hindi, Urdu)
            spoken_text = reply_text.replace("Saqib", "Saaqib") 
            voice = "en-IN-NeerjaNeural"
            
            communicate = edge_tts.Communicate(spoken_text, voice)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_mp3:
                await communicate.save(temp_mp3.name)
                temp_mp3_path = temp_mp3.name

            with open(temp_mp3_path, "rb") as mp3_file:
                await websocket.send_bytes(mp3_file.read())
            os.remove(temp_mp3_path)

    except WebSocketDisconnect:
        print("Client disconnected.")
                        
