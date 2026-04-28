"""VoteVibe: Election Process Education API Backend.

Enterprise-grade FastAPI backend with GCP multi-service architecture,
strict security headers, rate limiting, and Gemini AI integration.
"""
import os
import json
import logging
from typing import Any
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# GCP Enterprise SDKs (Auth, Storage, Firestore, Logging)
from google.cloud import firestore
from google.cloud import storage
import google.cloud.logging as cloud_logging
import firebase_admin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Security: Rate Limiting ---
limiter = Limiter(key_func=get_remote_address)

# --- Google Services Initialization ---
db = None
try:
    cloud_logger = cloud_logging.Client()
    cloud_logger.setup_logging()
    db = firestore.Client()
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    logger.info("GCP Multi-Service Architecture Initialized.")
except Exception as e:
    logger.warning(f"Running in limited IAM mode: {e}")

# --- Initialize FastAPI ---
app = FastAPI(title="VoteVibe API", version="2.0.0")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Security Middlewares ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next: Any) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

# --- Google GenAI Initialization (THE FIX) ---
load_dotenv()
# We force the app to use GEMINI_API_KEY and ignore system defaults
gemini_key = os.environ.get("GEMINI_API_KEY")

if gemini_key:
    # This explicit assignment stops the "Using GOOGLE_API_KEY" conflict
    client = genai.Client(api_key=gemini_key)
    logger.info("GenAI SDK initialized with forced GEMINI_API_KEY.")
else:
    client = None
    logger.warning("GEMINI_API_KEY is missing!")

class TimelineRequest(BaseModel):
    zip_code: str = Field(..., min_length=5, max_length=10)
    query: str = Field(..., min_length=3, max_length=500)

@app.get("/")
@limiter.limit("20/minute")
async def serve_index(request: Request) -> FileResponse:
    file_path = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(file_path)

@app.post("/api/election-timeline")
@limiter.limit("10/minute")
async def generate_timeline(request: Request, query_data: TimelineRequest) -> dict:
    if not client:
        raise HTTPException(status_code=500, detail="AI Service Key Missing.")

    system_instruction = (
        "You are a Civic Guide. Translate election rules into a simple, 3-step actionable JSON. "
        'Structure: {"steps": [{"step": 1, "action": "...", "details": "..."}, ...]} '
        "Return ONLY pure JSON."
    )

    try:
        # Using 2.0-flash as it is confirmed working with your current SDK/Quota
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=f"ZIP: {query_data.zip_code}\nQuery: {query_data.query}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            )
        )

        raw_text = response.text.strip()
        # Clean potential markdown wrapping
        if "```" in raw_text:
            raw_text = raw_text.split("```")[1].replace("json", "").strip()
        
        return json.loads(raw_text)

    except Exception as e:
        logger.error(f"Gemini API Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Timeline generation failed.")
