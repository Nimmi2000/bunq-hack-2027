"""
FastAPI backend for the Finn voice pipeline.

Runs on http://localhost:8000

Endpoints:
  GET  /health   — liveness check + active model name
  POST /voice    — audio file (WebM/OGG/MP3/WAV) → full pipeline → JSON
  POST /query    — plain text → Bedrock + bunq → JSON
"""

import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import voice_pipeline

app = FastAPI(title="Finn Voice Backend", version="1.0.0")

# Allow requests from the Streamlit iframe (localhost:8501) and any other origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "bedrock_model": os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
        "s3_bucket": os.environ.get("AWS_S3_BUCKET", "(not set)"),
        "bunq_key_set": bool(os.environ.get("BUNQ_API_KEY")),
    }


# ── Voice endpoint (audio → full pipeline) ────────────────────────────────────

@app.post("/voice")
async def voice_endpoint(audio: UploadFile = File(...)):
    """
    Accept a voice recording (WebM, OGG, MP3, WAV, FLAC) and run the full pipeline:
    Amazon Transcribe → Amazon Bedrock (tool use) → bunq API → natural language reply.
    """
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    try:
        result = voice_pipeline.run(
            audio_bytes,
            content_type=audio.content_type or "audio/webm",
        )
        return {"response": result, "status": "ok"}
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Query endpoint (text → pipeline, skipping STT) ───────────────────────────

class QueryRequest(BaseModel):
    text: str


@app.post("/query")
def query_endpoint(body: QueryRequest):
    """
    Accept a text query and run the Bedrock + bunq pipeline (STT step skipped).
    Use this when the client already has a transcript (e.g. from Web Speech API).
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty query.")
    try:
        result = voice_pipeline.run_text(body.text)
        return {"response": result, "status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
