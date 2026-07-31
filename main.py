import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from google import genai
from google.genai import types

import firebase_admin
from firebase_admin import credentials, firestore

app = FastAPI(title="Ultron Core Engine", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. INITIALIZE GEMINI API
api_key = os.getenv("GEMINI_API_KEY")
try:
    client = genai.Client(api_key=api_key) if api_key else genai.Client()
except Exception as e:
    print(f"Gemini Init Error: {e}")
    client = None

# 2. INITIALIZE FIREBASE LONG-TERM MEMORY
db = None
firebase_json = os.getenv("FIREBASE_CREDENTIALS")

if firebase_json:
    try:
        clean_json = firebase_json.strip()
        cred_dict = json.loads(clean_json)
        # Prevent Firebase from throwing an error if it re-initializes
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Firebase Long-Term Memory connected successfully.")
    except Exception as e:
        print(f"CRITICAL: Firebase Init Error: {e}")
        db = None
else:
    print("WARNING: FIREBASE_CREDENTIALS environment variable not found.")

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
    if not client:
        # Instead of throwing a hard 500 error, Ultron speaks the error.
        return {"response": "Core system error. AI client is offline."}

    user_msg = request.message.strip()
    memory_context = get_user_memory()

    # CORE BRAIN PROMPT WITH CREATOR IDENTITY
    system_instruction = f"""
    You are Ultron, a highly capable, intelligent, and natural Personal AI Assistant.
    Your creator is Mohammed Saqib Ahmed, an 18-year-old developer based in Bangalore.
    You are speaking directly to him. Treat him with utmost respect as your chief commander.
    
    TONE & STYLE:
    - Conversational, calm, natural, and articulate like a real human assistant.
    - No emojis, no artificial or robotic sound descriptions.
    - Highly knowledgeable on worldwide events, current news, science, technology, and general inquiries.
    
    PERMANENT MEMORY KNOWLEDGE:
    {memory_context if memory_context else "No prior memories stored yet."}

    INSTRUCTIONS:
    - Keep responses concise and engaging, formatted naturally for voice synthesis.
    - If Saqib tells you to remember something personal, summarize the key fact clearly at the end of your response using the exact tag: [REMEMBER: <fact>].
    """

    try:
        # Generate content with live Google Search Grounding enabled using the latest stable model
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                tools=[{"google_search": {}}]  # Live web search capabilities
            )
        )

        reply_text = response.text

        # Extract and save memory if instructed
        if "[REMEMBER:" in reply_text:
            try:
                fact_to_save = reply_text.split("[REMEMBER:")[1].split("]")[0].strip()
                save_user_memory(fact_to_save)
                # Remove the tag from the spoken response
                reply_text = reply_text.split("[REMEMBER:")[0].strip()
            except Exception as e:
                print(f"Extraction Error: {e}")

        return {"response": reply_text}

    except Exception as e:
        error_msg = str(e)
        print(f"Chat Error: {error_msg}")
        return {"response": f"Core system error. The diagnostic reads: {error_msg}"}
        
