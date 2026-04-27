"""
Voice package — speech-to-text via Groq Whisper API.

Endpoints:
  POST /voice/transcribe — upload audio, get transcribed text back.
  GET  /voice/status     — check if Groq API key is configured.

Calls Groq's Whisper API directly for fast transcription (~1-2s).
Uses GROQ_API_KEY from ~/.hermes/.env (loaded by env_setup at bridge boot).
"""

import os
import tempfile
import time

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse

router = APIRouter()

GROQ_API_KEY = None  # Resolved lazily
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "whisper-large-v3-turbo"


def _get_groq_key() -> str:
    """Resolve the Groq API key from env (loaded by bridge bootstrap)."""
    global GROQ_API_KEY
    if GROQ_API_KEY:
        return GROQ_API_KEY
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    return GROQ_API_KEY


@router.get("/voice/status")
async def voice_status():
    """Check if Groq API key is configured.
    
    Returns connection status and key preview for UI display.
    """
    api_key = _get_groq_key()
    
    if not api_key:
        return JSONResponse({
            "connected": False,
            "has_key": False,
            "key_preview": None,
            "provider": "groq",
        })
    
    # Show last 4 characters of key
    key_preview = f"•••{api_key[-4:]}" if len(api_key) > 4 else "••••"
    
    return JSONResponse({
        "connected": True,
        "has_key": True,
        "key_preview": key_preview,
        "provider": "groq",
    })


@router.post("/voice/transcribe")
async def transcribe_voice(file: UploadFile = File(...)):
    """Receive audio from the frontend and transcribe via Groq.

    Fast path: Groq Whisper API processes audio in ~1-2 seconds.
    No heavy imports, no auto-detection — just fast transcription.
    """
    api_key = _get_groq_key()
    if not api_key:
        return JSONResponse(
            {
                "success": False,
                "error": "GROQ_API_KEY not set in ~/.hermes/.env",
            },
            status_code=500,
        )

    start = time.time()

    # Save uploaded audio to temp file
    suffix = os.path.splitext(file.filename or "voice.webm")[1] or ".webm"
    try:
        with tempfile.NamedTemporaryFile(
            suffix=suffix, prefix="hemui-voice-", delete=False
        ) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": f"Failed to save audio: {e}"},
            status_code=500,
        )

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=GROQ_BASE_URL,
            timeout=15,
            max_retries=0,
        )

        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=GROQ_MODEL,
                file=audio_file,
                response_format="text",
            )

        transcript = str(transcription).strip()
        elapsed = time.time() - start

        print(f"[VOICE] Groq transcribed in {elapsed:.1f}s: {transcript[:80]!r}")

        # Close the client
        close = getattr(client, "close", None)
        if callable(close):
            close()

        return JSONResponse({
            "success": True,
            "transcript": transcript,
            "provider": "groq",
            "elapsed": round(elapsed, 2),
        })

    except Exception as e:
        elapsed = time.time() - start
        print(f"[VOICE] Error after {elapsed:.1f}s: {e}")
        return JSONResponse(
            {"success": False, "error": f"Transcription failed: {e}"},
            status_code=500,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
