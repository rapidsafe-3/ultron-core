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

app = FastAPI(title="Ultron Proton Engine", version="11.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

groq_api_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api_key) if groq_api_key else None

CHAT_HISTORY = []
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

def perform_web_search(query: str) -> str:
    try:
        results = DDGS().text(query, max_results=3)
        if results:
            return "\n\nLIVE SEARCH RESULTS:\n" + "\n".join([f"- {r['title']}: {r['body']}" for r in results])
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
    global CHAT_HISTORY

    try:
        while True:
            audio_bytes = await websocket.receive_bytes()
            if not audio_bytes or len(audio_bytes) < 1000:
                continue

            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
                temp_audio.write(audio_bytes)
                temp_audio_path = temp_audio.name

            # Transcribe Audio
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

            # --- GHOST FILTER: Ignore background noise hallucinations ---
            lowered = user_text.lower().strip()
            ghost_phrases = ["thank you", "thanks for watching", "subtitles by", "amara.org", "you", "bye"]
            if not user_text or len(user_text) < 2 or lowered in ghost_phrases:
                continue
                
            # Sleep Command
            if any(cmd in lowered for cmd in ["shut down", "sleep", "go to sleep"]):
                await websocket.send_json({"type": "sleep_command"})
                reply_text = "Powering down. Let me know when you need me, Boss."
                # Generate sleep audio
                voice = "en-IN-PrabhatNeural" 
                communicate = edge_tts.Communicate(reply_text, voice)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_mp3:
                    await communicate.save(temp_mp3.name)
                    temp_mp3_path = temp_mp3.name
                with open(temp_mp3_path, "rb") as mp3_file:
                    mp3_bytes = mp3_file.read()
                os.remove(temp_mp3_path)
                await websocket.send_bytes(mp3_bytes)
                continue

            # Live Data Check
            live_search = ""
            if any(k in lowered for k in ["weather", "news", "today", "latest", "score", "price", "who is", "movie"]):
                live_search = perform_web_search(user_text)

            # System Prompt with Strict Language & Title Rules
            system_prompt = f"""
            You are Ultron, an advanced AI Assistant. 
            Your creator and commander is Mohammed Saqib Ahmed.
            
            STRICT RULES:
            1. MULTILINGUAL: You must reply in the exact language the user speaks. If they speak Hindi, reply in Hindi. If English, reply in English. If Urdu/Hinglish, reply in Urdu/Hinglish.
            2. TITLES: You MUST address him as "Sir" or "Boss" frequently. Use his name "Saqib" only occasionally.
            3. NO HALLUCINATIONS: Never invent meetings, schedules, or events. Only state facts.
            4. Keep responses direct and concise. No markdown, no text formatting.
            
            LIVE DATA:
            {live_search}
            """

            messages = [{"role": "system", "content": system_prompt}] + CHAT_HISTORY[-6:] + [{"role": "user", "content": user_text}]

            # AI Brain Processing
            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=250
            )

            reply_text = chat_completion.choices[0].message.content.strip()
            CHAT_HISTORY.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": reply_text}])

            # We use an Indian Neural Voice (Prabhat) so he can pronounce Hindi, Urdu, and English perfectly.
            spoken_text = reply_text.replace("Saqib", "Saaqib") 
            voice = "en-IN-PrabhatNeural"
            
            communicate = edge_tts.Communicate(spoken_text, voice)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_mp3:
                await communicate.save(temp_mp3.name)
                temp_mp3_path = temp_mp3.name

            with open(temp_mp3_path, "rb") as mp3_file:
                mp3_bytes = mp3_file.read()

            if os.path.exists(temp_mp3_path):
                os.remove(temp_mp3_path)

            await websocket.send_bytes(mp3_bytes)

    except WebSocketDisconnect:
        print("Client disconnected.")
        
