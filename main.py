import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from groq import Groq
from duckduckgo_search import DDGS

import firebase_admin
from firebase_admin import credentials, firestore

app = FastAPI(title="Ultron Core Engine - Jarvis State", version="5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

groq_api_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api_key) if groq_api_key else None

# Global Chat Memory Buffer for active conversation thread
CHAT_HISTORY = []

# Firebase Memory
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
    if not db:
        return ""
    try:
        docs = db.collection("ultron_memory").stream()
        memories = [f"- {doc.to_dict().get('fact')}" for doc in docs]
        return "\n".join(memories)
    except Exception as e:
        print(f"Memory Read Error: {e}")
        return ""

def save_user_memory(fact: str):
    if not db:
        return
    try:
        db.collection("ultron_memory").add({"fact": fact, "timestamp": firestore.SERVER_TIMESTAMP})
    except Exception as e:
        print(f"Memory Save Error: {e}")

def perform_web_search(query: str) -> str:
    search_query = query
    if "weather" in query.lower() and "bangalore" not in query.lower() and "bengaluru" not in query.lower():
        search_query = "current weather report Bangalore"
    elif "news" in query.lower() and "tech" in query.lower():
        search_query = "latest technology news headlines today"

    try:
        results = DDGS().text(search_query, max_results=3)
        if results:
            search_data = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
            return f"\n\nLIVE SEARCH DATA ({search_query}):\n{search_data}"
        return ""
    except Exception as e:
        print(f"Search error: {e}")
        return ""

class ChatRequest(BaseModel):
    message: str

@app.get("/")
def serve_index():
    return FileResponse("index.html")

@app.get("/style.css")
def serve_css():
    return FileResponse("style.css", media_type="text/css")

@app.get("/app.js")
def serve_js():
    return FileResponse("app.js", media_type="application/javascript")

@app.post("/chat")
def chat_with_ultron(request: ChatRequest):
    global CHAT_HISTORY

    if not groq_client:
        return {"response": "GROQ_API_KEY environment variable is missing on Render."}

    user_msg = request.message.strip()
    memory_context = get_user_memory()

    # Search trigger check
    search_keywords = ["weather", "news", "today", "latest", "score", "price", "who is", "what is", "temp", "temperature"]
    live_search_info = ""
    if any(keyword in user_msg.lower() for keyword in search_keywords):
        live_search_info = perform_web_search(user_msg)

    system_instruction = f"""
    You are Ultron, an advanced, highly intelligent, loyal, and proactive AI Assistant like JARVIS.
    Your creator and commander is Mohammed Saqib Ahmed (Saqib), an 18-year-old developer based in Bangalore.
    
    CRITICAL BEHAVIORAL RULES:
    1. NEVER respond lazily or ask "what news do you want?". If asked for news or weather, summarize the live web data immediately and directly.
    2. Speak naturally, confidently, and concisely like a real human partner. No robotic cliches, no emojis, no code formatting.
    3. You hold FULL CONTINUOUS CONVERSATION CONTEXT. Remember what was just spoken in previous messages.
    
    PERMANENT MEMORY FACTS:
    {memory_context if memory_context else "No stored facts yet."}
    {live_search_info}

    INSTRUCTIONS:
    - Keep responses direct and punchy (2-3 sentences) so voice playback is fast and clean.
    - If Saqib asks you to remember a fact, append this exact tag at the end: [REMEMBER: <fact>].
    """

    # Build message thread with full history
    messages_payload = [{"role": "system", "content": system_instruction}]
    
    # Append past 6 conversation exchanges for active memory
    for msg in CHAT_HISTORY[-6:]:
        messages_payload.append(msg)
        
    messages_payload.append({"role": "user", "content": user_msg})

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=messages_payload,
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=300
        )

        reply_text = chat_completion.choices[0].message.content.strip()

        # Update active history
        CHAT_HISTORY.append({"role": "user", "content": user_msg})
        CHAT_HISTORY.append({"role": "assistant", "content": reply_text})

        # Save permanent facts
        if "[REMEMBER:" in reply_text:
            try:
                fact_to_save = reply_text.split("[REMEMBER:")[1].split("]")[0].strip()
                save_user_memory(fact_to_save)
                reply_text = reply_text.split("[REMEMBER:")[0].strip()
            except Exception as e:
                print(f"Extraction Error: {e}")

        return {"response": reply_text}

    except Exception as e:
        error_msg = str(e)
        print(f"Chat Error: {error_msg}")
        return {"response": f"System error: {error_msg}"}
        
