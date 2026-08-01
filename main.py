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

app = FastAPI(title="Ultron Core - JARVIS Edition", version="7.0")

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
    search_query = query
    if "weather" in query.lower() and "bangalore" not in query.lower():
        search_query = "current weather report Bangalore"
    try:
        results = DDGS().text(search_query, max_results=3)
        if results:
            return "\n\nLIVE WEB DATA:\n" + "\n".join([f"- {r['title']}: {r['body']}" for r in results])
        return ""
    except:
        return ""

@app.get("/")
def serve_index(): return FileResponse("index.html")

@app.get("/style.css")
def serve_css(): return FileResponse("style.css", media_type="text/css")

@app.get("/app.js")
def serve_js(): return FileResponse("app.js", media_type="application/javascript")

# --- ULTRA-FAST WEBSOCKET PIPELINE ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    global CHAT_HISTORY

    try:
        while True:
            # 1. Receive instant audio bytes from phone
            audio_bytes = await websocket.receive_bytes()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
                temp_audio.write(audio_bytes)
                temp_audio_path = temp_audio.name

            # 2. Instant Transcription (Groq Whisper)
            try:
                with open(temp_audio_path, "rb") as file:
                    transcription = groq_client.audio.transcriptions.create(
                        file=(temp_audio_path, file.read()),
                        model="whisper-large-v3",
                        language="en"
                    )
                user_text = transcription.text.strip()
            except Exception as e:
                user_text = ""
            finally:
                os.remove(temp_audio_path)

            if not user_text:
                continue

            # Send transcribed text to UI instantly
            await websocket.send_json({"type": "transcript", "text": user_text})

            # 3. Brain Processing (Groq Llama 3)
            memory_context = get_user_memory()
            live_search = perform_web_search(user_text) if any(k in user_text.lower() for k in ["weather", "news", "today", "score"]) else ""

            system_prompt = f"""
            You are Ultron, a highly advanced, JARVIS-like AI Assistant.
            Your creator is Mohammed Saqib Ahmed (Saqib), an 18-year-old developer in Bangalore.
            
            RULES:
            - Respond instantly, confidently, and concisely (1-3 sentences).
            - Do not ask follow-up questions for news/weather; just deliver the facts.
            - No markdown, no emojis.
            
            MEMORY:
            {memory_context}
            {live_search}
            """

            messages = [{"role": "system", "content": system_prompt}] + CHAT_HISTORY[-4:] + [{"role": "user", "content": user_text}]
            
            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=250
            )
            
            reply_text = chat_completion.choices[0].message.content.strip()

            if "[REMEMBER:" in reply_text:
                fact = reply_text.split("[REMEMBER:")[1].split("]")[0].strip()
                save_user_memory(fact)
                reply_text = reply_text.split("[REMEMBER:")[0].strip()

            CHAT_HISTORY.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": reply_text}])

            # Send UI text response
            await websocket.send_json({"type": "response_text", "text": reply_text})

            # 4. Instant Neural TTS Generation
            voice = "en-GB-RyanNeural"
            communicate = edge_tts.Communicate(reply_text, voice)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_mp3:
                await communicate.save(temp_mp3.name)
                temp_mp3_path = temp_mp3.name

            with open(temp_mp3_path, "rb") as audio_file:
                mp3_bytes = audio_file.read()
            os.remove(temp_mp3_path)

            # Stream audio bytes directly back to the phone
            await websocket.send_bytes(mp3_bytes)

    except WebSocketDisconnect:
        print("Client disconnected.")
