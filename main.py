import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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

# Render will automatically inject your GEMINI_API_KEY from its dashboard
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
You now have memory of this conversation. Use context from past messages.
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

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    try:
        with open("index.html", "r") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Error: index.html not found!</h1>"

@app.post("/chat")
def chat_with_ultron(request: ChatRequest):
    if not client:
         raise HTTPException(status_code=500, detail="AI offline.")
    try:
        response = ultron_memory.send_message(request.message)
        return {"response": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
      
