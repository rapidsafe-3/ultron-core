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
        cred_dict = json.loads(firebase_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Firebase Long-Term Memory connected successfully.")
    except Exception as e:
        print(f"Firebase Init Error: {e}")

# Helper functions for Long-Term Memory
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
        raise HTTPException(status_code=500, detail="Ultron AI Client Offline.")

    user_msg = request.message.strip()

    # Retrieve existing memories from Firebase
    memory_context = get_user_memory()

    # Persona System Prompt
    system_instruction = f"""
    You are Ultron, a highly capable, intelligent, and natural Personal AI Assistant speaking to your creator.
    
    TONE & STYLE:
    - Conversational, calm, natural, and articulate like a real human assistant.
    - No emojis, no artificial or robotic sound descriptions.
    - Highly knowledgeable on worldwide events, current news, science, technology, and general inquiries.
    
    PERMANENT MEMORY KNOWLEDGE:
    {memory_context if memory_context else "No prior memories stored yet."}

    INSTRUCTIONS:
    - Treat the user as your sole creator and chief commander.
    - Keep responses concise and engaging, formatted naturally for voice synthesis.
    - If the user tells you to remember something personal (e.g. "Remember my name is...", "Remember that I like..."), summarize the key fact clearly at the end of your response using tag: [REMEMBER: <fact>].
    """

    try:
        # Generate content with live Google Search Grounding enabled
        response = client.models.generate_content(
            model="gemini-2.5-flash",
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
                # Remove tag from spoken response
                reply_text = reply_text.split("[REMEMBER:")[0].strip()
            except Exception as e:
                print(f"Extraction Error: {e}")

        return {"response": reply_text}

    except Exception as e:
        print(f"Chat Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
