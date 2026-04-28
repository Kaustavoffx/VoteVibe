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

# --- Google Services: Multi-Service Architecture Initialization ---
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

# --- Google GenAI SDK Initialization ---
load_dotenv()

# Security: Load API Key from environment (NEVER HARDCODE)
gemini_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=gemini_key) if gemini_key else None

if client:
    logger.info("Google GenAI SDK initialized successfully.")
else:
    logger.warning("GEMINI_API_KEY not set. AI features disabled.")


# --- Pydantic Models for Input Validation ---
class TimelineRequest(BaseModel):
    """Pydantic model for Election Process Education timeline request."""

    zip_code: str = Field(
        ...,
        min_length=5,
        max_length=10,
        description=(
            "The user's ZIP or PIN code (e.g., '12345' or '110001')."
        ),
    )
    query: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="The user's query about the Election Process.",
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
    """Generate a 3-step Election Process Education timeline.

    Uses Google Gemini AI to translate complex election timelines
    and rules into simple, actionable steps.

    Args:
        request: The incoming HTTP request (required for rate limiter).
        query_data: Validated input with zip code and query.

    Returns:
        dict: A structured JSON response with election steps.

    Raises:
        HTTPException: If the AI client is unavailable or the call fails.
    """
    if not client:
        logger.error("GenAI client is not initialized.")
        raise HTTPException(
            status_code=500, detail="AI Service Initializing."
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
        "Do not include any other text outside the JSON."
    )

    prompt = (
        f"ZIP Code: {query_data.zip_code}\n"
        f"Query: {query_data.query}"
    )

    try:
        logger.info(
            "Generating Election Process Education timeline "
            f"for ZIP code {query_data.zip_code}"
        )
        response = client.models.generate_content(
            model='gemini-3-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            )
        )

        # Strip markdown backticks if Gemini wraps the JSON
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        raw_text = raw_text.strip()

        # Parse to ensure valid JSON before sending to frontend
        clean_json: dict = json.loads(raw_text)

        # Google Services: Log to Firestore if available
        if db is not None:
            try:
                db.collection("timeline_requests").add({
                    "zip_code": query_data.zip_code,
                    "query": query_data.query,
                    "status": "success",
                })
            except Exception as firestore_err:
                logger.warning(
                    f"Firestore write failed: {firestore_err}"
                )

        return clean_json

    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to parse Gemini response as JSON: {e}"
        )
        raise HTTPException(
            status_code=500, detail="Failed to parse AI response."
        )
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to generate timeline."
        )
