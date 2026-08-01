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

app = FastAPI(title="Ultron Neural Engine", version="9.0")

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

# Live Real-World Search Engine
def perform_web_search(query: str) -> str:
    try:
        results = DDGS().text(query, max_results=4)
        if results:
            return "\n\nLIVE SEARCH RESULTS:\n" + "\n".join([f"- {r['title']}: {r['body']}" for r in results])
        return ""
    except Exception as e:
        print(f"Search Error: {e}")
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
            # Receive raw audio bytes recorded automatically by client VAD
            audio_bytes = await websocket.receive_bytes()
            if not audio_bytes or len(audio_bytes) < 1000:
                continue

            # Save temporary webm file for Whisper
            with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
                temp_audio.write(audio_bytes)
                temp_audio_path = temp_audio.name

            # 1. High-Precision Speech-to-Text via Groq Whisper V3
            try:
                with open(temp_audio_path, "rb") as audio_file:
                    transcription = groq_client.audio.transcriptions.create(
                        file=(temp_audio_path, audio_file.read()),
                        model="whisper-large-v3",
                        language="en"
                    )
                user_text = transcription.text.strip()
            except Exception as e:
                print(f"Whisper STT Error: {e}")
                user_text = ""
            finally:
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)

            if not user_text or len(user_text) < 2:
                continue

            # Send transcript back to UI
            await websocket.send_json({"type": "transcript", "text": user_text})

            # 2. Live Web Grounding + Memory Context
            live_search = ""
            search_keywords = ["weather", "news", "today", "latest", "score", "price", "who is", "what is", "movie", "release"]
            if any(k in user_text.lower() for k in search_keywords):
                search_query = user_text
                if "weather" in user_text.lower() and "bangalore" not in user_text.lower():
                    search_query += " Bangalore"
                live_search = perform_web_search(search_query)

            memory_context = get_user_memory()

            system_prompt = f"""
            You are Ultron, an advanced, highly capable, loyal AI Assistant like JARVIS.
            Your creator and commander is Mohammed Saqib Ahmed (Saqib), an 18-year-old developer based in Bangalore.
            
            CORE BEHAVIOR RULES:
            - Respond naturally, confidently, and directly like a human assistant.
            - Provide clear facts directly without asking counter-questions.
            - Maintain continuous conversation awareness across messages.
            
            MEMORY & LIVE DATA:
            {memory_context}
            {live_search}

            INSTRUCTIONS:
            - Keep responses concise and engaging (2-3 sentences) for clean voice synthesis.
            - If Saqib asks you to remember a fact, append this exact tag at the end: [REMEMBER: <fact>].
            """

            messages = [{"role": "system", "content": system_prompt}] + CHAT_HISTORY[-6:] + [{"role": "user", "content": user_text}]

            # 3. Brain Processing via Llama 3.3 70B
            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=300
            )

            reply_text = chat_completion.choices[0].message.content.strip()

            if "[REMEMBER:" in reply_text:
                fact = reply_text.split("[REMEMBER:")[1].split("]")[0].strip()
                save_user_memory(fact)
                reply_text = reply_text.split("[REMEMBER:")[0].strip()

            CHAT_HISTORY.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": reply_text}])

            await websocket.send_json({"type": "response_text", "text": reply_text})

            # 4. Neural Voice Generation
            voice = "en-GB-RyanNeural"
            communicate = edge_tts.Communicate(reply_text, voice)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_mp3:
                await communicate.save(temp_mp3.name)
                temp_mp3_path = temp_mp3.name

            with open(temp_mp3_path, "rb") as mp3_file:
                mp3_bytes = mp3_file.read()

            if os.path.exists(temp_mp3_path):
                os.remove(temp_mp3_path)

            # Stream speech audio back over WebSocket
            await websocket.send_bytes(mp3_bytes)

    except WebSocketDisconnect:
        print("Client disconnected.")
                
