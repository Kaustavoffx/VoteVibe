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
from firebase_admin import credentials  # noqa: F401

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
storage_client = None

try:
    cloud_logger = cloud_logging.Client()
    cloud_logger.setup_logging()
    db = firestore.Client()
    storage_client = storage.Client()
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    logger.info(
        "GCP Multi-Service Architecture Initialized: "
        "Auth, Storage, Firestore, Logging."
    )
except Exception as e:
    logger.warning(f"Running in degraded IAM mode: {e}")

# --- Initialize FastAPI Application ---
app = FastAPI(
    title="VoteVibe: Election Process Education API",
    description=(
        "A highly secure, efficient FastAPI backend "
        "for the VoteVibe Election Process Education PWA."
    ),
    version="2.0.0"
)

# Attach rate limiter to the app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# --- Security: Custom HTTP Security Headers Middleware ---
@app.middleware("http")
async def add_security_headers(
    request: Request, call_next: Any
) -> Response:
    """Inject enterprise-grade security headers into every response."""
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = (
        "strict-origin-when-cross-origin"
    )

    # Cache-Control for GET requests
    if request.method == "GET":
        response.headers["Cache-Control"] = "public, max-age=3600"
    else:
        response.headers["Cache-Control"] = "no-store"

    return response


# --- Security & Efficiency Middlewares ---
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# --- Google GenAI SDK Initialization (FIXED) ---
load_dotenv()

# Security: Load ONLY GEMINI_API_KEY to avoid conflict
gemini_key = os.environ.get("GEMINI_API_KEY")

if gemini_key:
    # Forced explicit assignment
    client = genai.Client(api_key=gemini_key)
    logger.info("Google GenAI SDK initialized with forced GEMINI_API_KEY.")
else:
    client = None
    logger.warning("GEMINI_API_KEY not set. AI features disabled.")


# --- Pydantic Models for Input Validation ---
class TimelineRequest(BaseModel):
    """Pydantic model for Election Process Education timeline request."""
    zip_code: str = Field(
        ...,
        min_length=5,
        max_length=10,
        description="The user's ZIP or PIN code."
    )
    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="The user's query about the Election Process."
    )


# --- Core Logic Endpoints ---
@app.get("/")
@limiter.limit("20/minute")
async def serve_index(request: Request) -> FileResponse:
    """Serve the Election Process Education frontend."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "index.html")

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404, detail="index.html not found"
        )

    return FileResponse(file_path)


@app.post("/api/election-timeline")
@limiter.limit("10/minute")
async def generate_timeline(
    request: Request, query_data: TimelineRequest
) -> dict:
    """Generate a 3-step Election Process Education timeline using Gemini AI."""
    
    if not client:
        logger.error("GenAI client is not initialized.")
        raise HTTPException(
            status_code=500, detail="AI Service Key Missing or Initializing."
        )

    system_instruction = (
        "You are a Civic Guide for Election Process Education. "
        "Your task is to translate complex election timelines and rules "
        "into a simple, 3-step actionable JSON response based on the "
        "user's ZIP code and query. "
        "The JSON MUST follow this exact structure: "
        '{"steps": [{"step": 1, "action": "...", "details": "..."}, '
        '{"step": 2, "action": "...", "details": "..."}, '
        '{"step": 3, "action": "...", "details": "..."}]} '
        "Return ONLY the raw JSON string. Do not include markdown formatting or backticks."
    )

    try:
        logger.info(f"Processing request for ZIP: {query_data.zip_code}")
        
        response = client.models.generate_content(
            model='gemini-2.0-flash', # Stable high-speed model
            contents=f"ZIP: {query_data.zip_code}, Query: {query_data.query}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            )
        )

        # Parse response safely
        raw_text = response.text.strip()
        
        # Strip potential markdown backticks if AI ignores instruction
        if "```" in raw_text:
            raw_text = raw_text.split("```")[1].replace("json", "").strip()
        
        clean_json: dict = json.loads(raw_text)

        # Firestore Logging
        if db is not None:
            try:
                db.collection("timeline_requests").add({
                    "zip_code": query_data.zip_code,
                    "query": query_data.query,
                    "status": "success",
                })
            except Exception as fe:
                logger.warning(f"Firestore error: {fe}")

        return clean_json

    except Exception as e:
        logger.error(f"Error calling Gemini API: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to generate timeline. Check API quota."
        )
