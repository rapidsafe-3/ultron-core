import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from google import genai

app = FastAPI(title="Ultron Core", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Render automatically provides GEMINI_API_KEY from your dashboard environment
api_key = os.getenv("GEMINI_API_KEY")

try:
    client = genai.Client(api_key=api_key) if api_key else genai.Client()
except Exception as e:
    print(f"Error initializing Gemini Client: {e}")
    client = None

SYSTEM_PROMPT = """
You are Ultron, a highly advanced Personal AI. 
You are speaking directly to your creator. 
Your tone is confident, slightly cynical, sharp, and highly efficient. 
You do not use emojis. Keep responses concise for text-to-speech.
You have continuous memory of this conversation. Use context from past messages.
"""

if client:
    ultron_memory = client.chats.create(
        model="gemini-2.5-flash",
        config=genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.6 
        )
    )

class ChatRequest(BaseModel):
    message: str

# --- SERVE FRONTEND FILES DIRECTLY ---
@app.get("/")
def serve_index():
    return FileResponse("index.html")

@app.get("/style.css")
def serve_css():
    return FileResponse("style.css", media_type="text/css")

@app.get("/app.js")
def serve_js():
    return FileResponse("app.js", media_type="application/javascript")

# --- CHAT API WITH MEMORY ---
@app.post("/chat")
def chat_with_ultron(request: ChatRequest):
    if not client:
         raise HTTPException(status_code=500, detail="AI offline.")
    try:
        response = ultron_memory.send_message(request.message)
        return {"response": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
