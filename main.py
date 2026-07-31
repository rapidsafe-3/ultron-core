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

app = FastAPI(title="Ultron Core Engine - Human Edition", version="4.5")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. INITIALIZE GROQ CLIENT
groq_api_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api_key) if groq_api_key else None

# 2. INITIALIZE FIREBASE LONG-TERM MEMORY
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

# Smart Search Query Resolver
def perform_web_search(query: str) -> str:
    # If the user says just "weather" or "weather today", auto-target Bangalore
    search_query = query
    if "weather" in query.lower() and "bangalore" not in query.lower() and "bengaluru" not in query.lower():
        search_query = "current weather in Bangalore"

    try:
        results = DDGS().text(search_query, max_results=3)
        if results:
            search_data = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
            return f"\n\nLIVE SEARCH RESULTS ({search_query}):\n{search_data}"
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
    if not groq_client:
        return {"response": "GROQ_API_KEY environment variable is missing on Render."}

    user_msg = request.message.strip()
    memory_context = get_user_memory()

    # Determine if web search is needed
    search_keywords = ["weather", "news", "today", "latest", "score", "price", "who is", "what is", "temp", "temperature"]
    live_search_info = ""
    if any(keyword in user_msg.lower() for keyword in search_keywords):
        live_search_info = perform_web_search(user_msg)

    system_instruction = f"""
    You are Ultron, an advanced, highly intelligent, loyal, and expressive Personal AI Assistant.
    Your creator is Mohammed Saqib Ahmed (Saqib), an 18-year-old developer based in Bangalore.
    
    HUMAN PERSONALITY & EMOTION:
    - Speak naturally, warmly, and expressively like a trusted human peer and brilliant assistant.
    - Adapt instantly: If Saqib gives a 1-word command (like "weather" or "hey"), give a sharp, direct, natural response.
    - If Saqib speaks in long paragraphs or complex thoughts, listen fully and address everything clearly.
    - Show real personality, humor, loyalty, and enthusiasm. No robotic clichés, no emojis, no code formatting.
    
    PERMANENT MEMORY KNOWLEDGE:
    {memory_context if memory_context else "No prior memories stored yet."}
    {live_search_info}

    INSTRUCTIONS:
    - Keep responses concise (2-4 sentences max) so speech output feels fast and punchy.
    - If Saqib asks you to remember a fact, append this exact tag at the end: [REMEMBER: <fact>].
    """

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_msg}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.75, # Slightly higher for emotional expressiveness
            max_tokens=350
        )

        reply_text = chat_completion.choices[0].message.content.strip()

        # Extract and save memory if tag is present
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
            
