import os
import json
import tempfile
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from groq import Groq
from duckduckgo_search import DDGS
import edge_tts

import firebase_admin
from firebase_admin import credentials, firestore

app = FastAPI(title="Ultron Core - JARVIS Edition", version="8.0")

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

# Enhanced Web Search for Real World Data
def perform_web_search(query: str) -> str:
    try:
        results = DDGS().text(query, max_results=4)
        if results:
            return "\n\nLIVE WEB DATA:\n" + "\n".join([f"- {r['title']}: {r['body']}" for r in results])
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
            # 1. Receive text query from frontend
            data = await websocket.receive_json()
            if data.get("type") != "text_query":
                continue
                
            user_text = data.get("text", "")
            
            # 2. Pull Real World Data (Search everything by default for maximum accuracy)
            live_search = perform_web_search(user_text) 
            memory_context = get_user_memory()

            # 3. Process with Brain
            system_prompt = f"""
            You are Ultron, a highly advanced, proactive AI Assistant. 
            Your creator is Saqib.
            
            RULES:
            - Respond instantly and directly.
            - Speak naturally, like a brilliant human partner.
            - Rely heavily on the LIVE WEB DATA provided to answer questions accurately. 
            - Keep answers punchy and conversational (1-3 sentences).
            
            MEMORY & CONTEXT:
            {memory_context}
            {live_search}
            """

            messages = [{"role": "system", "content": system_prompt}] + CHAT_HISTORY[-6:] + [{"role": "user", "content": user_text}]
            
            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=250
            )
            
            reply_text = chat_completion.choices[0].message.content.strip()

            # Memory Tag check
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

            # Stream audio bytes directly back
            await websocket.send_bytes(mp3_bytes)

    except WebSocketDisconnect:
        print("Client disconnected.")
        
