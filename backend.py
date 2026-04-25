"""
FastAPI backend for the Finn voice pipeline.

Runs on http://localhost:8000

Endpoints:
  GET  /health              — liveness check + active model name
  POST /voice               — audio file (WebM/OGG/MP3/WAV) → full pipeline → JSON
  POST /query               — plain text → Bedrock + bunq → JSON
  POST /enroll/{user_id}    — image → Rekognition enrollment → JSON
  POST /query-with-frame    — text + camera frame → fraud check → bunq → JSON
  GET  /risk/{session_id}   — last fraud analysis result for session
"""

import asyncio
import base64 as _b64
import datetime
import os
import re
from pathlib import Path
from typing import Optional

DEBUG_DIR = Path(__file__).parent / "debug_frames"
DEBUG_DIR.mkdir(exist_ok=True)

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import voice_pipeline

app = FastAPI(title="Finn Voice Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory stores (reset on restart) ──────────────────────────────────────

_risk_store: dict[str, dict] = {}        # session_id → last risk analysis
_pending_payments: dict[str, dict] = {}  # session_id → held payment details

# ── Fraud analysis helpers ────────────────────────────────────────────────────

_PAYMENT_KEYWORDS = {"send", "pay", "transfer", "payment", "request", "invoice", "charge", "link"}


def _is_payment_intent(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _PAYMENT_KEYWORDS)


def _log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}", flush=True)


def _run_fraud_analysis(image_bytes: bytes, text: str) -> dict:
    """
    Run all three detection layers synchronously and return a risk dict.
    Prints progress to the terminal as each layer completes.
    """
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    frame_path = DEBUG_DIR / f"frame_{ts}.jpg"
    frame_path.write_bytes(image_bytes)

    _log("=" * 60)
    _log(f"FRAUD ANALYSIS  query='{text[:70]}'  frame={frame_path.name}  ({len(image_bytes)//1024} KB)")
    _log("=" * 60)

    try:
        from detection import moire_glare, claude_vision, rekognition
        import risk_engine
    except ImportError as exc:
        _log(f"ERROR: Detection modules not available: {exc}")
        return {
            "risk_score": 0.0,
            "recommendation": "ALLOW",
            "reason": f"Detection modules not available: {exc}",
            "signals": {},
        }

    # ── Layer 1: optical screen-replay signals ────────────────────────────────
    _log("Layer 1 → Optical screen-replay detection (moire/glare)…")
    try:
        screen = moire_glare.analyze(image_bytes)
    except Exception as exc:
        screen = {"screen_replay_flag": False, "moire_peak_ratio": 0.0,
                  "glare_regions": 0, "dark_corners": 0, "error": str(exc)}
    _log(
        f"  screen_replay={screen.get('screen_replay_flag')}  "
        f"moire_peak={screen.get('moire_peak_ratio', 0):.3f}  "
        f"glare_regions={screen.get('glare_regions', 0)}  "
        + (f"error={screen['error']}" if "error" in screen else "")
    )

    # ── Layer 2: face enrollment check ───────────────────────────────────────
    _log("Layer 2 → Face verification…")
    enrolled = rekognition.load_enrolled()
    user_is_enrolled = "eva" in enrolled
    face_quality = {"quality_ok": True}
    face_match = {"matched": False, "similarity": 0.0, "method": "default"}
    _log(f"  enrolled_user={'eva' if user_is_enrolled else '(none)'}")

    try:
        try:
            face_quality = rekognition.get_face_quality(image_bytes)
            _log(f"  face_quality: ok={face_quality.get('quality_ok')}  "
                 f"sharpness={face_quality.get('sharpness', 0):.1f}  "
                 f"brightness={face_quality.get('brightness', 0):.1f}  "
                 f"faces_detected={face_quality.get('face_count', '?')}")
        except Exception as exc:
            _log(f"  face_quality: unavailable ({exc})")

        rek_result = rekognition.compare_face(image_bytes, user_id="eva")

        if not rek_result.get("error"):
            face_match = rek_result
            _log(f"  rekognition: matched={face_match.get('matched')}  similarity={face_match.get('similarity')}%")
        elif user_is_enrolled:
            _log(f"  rekognition unavailable ({rek_result.get('error')}) → falling back to Claude Vision…")
            enrolled_b64 = enrolled.get("eva", {}).get("enrolled_image_b64")
            if enrolled_b64:
                enrolled_img = _b64.b64decode(enrolled_b64)
                cv_compare = claude_vision.compare_faces(image_bytes, enrolled_img)
                same = cv_compare.get("same_person")
                conf = float(cv_compare.get("confidence", 0.0))
                confirmed = (same is True) and (conf >= 0.92)
                face_match = {
                    "matched": confirmed,
                    "similarity": round(conf * 100, 1),
                    "method": "claude_vision",
                }
                _log(f"  claude_vision compare: same_person={same}  confidence={conf:.2f}  "
                     f"→ confirmed={confirmed}  reason={cv_compare.get('reason', '')}")
            else:
                _log("  no enrolled_image_b64 found → face_match stays False")
    except Exception as exc:
        face_match = {"matched": False, "similarity": 0.0, "method": "error", "error": str(exc)}
        _log(f"  EXCEPTION in face check: {exc}")

    _log(f"  face_match FINAL: matched={face_match.get('matched')}  "
         f"similarity={face_match.get('similarity')}%  method={face_match.get('method')}")

    # ── Layer 3: Claude Vision deepfake / coercion analysis ───────────────────
    _log("Layer 3 → Claude Vision deepfake/coercion analysis…")
    try:
        if screen.get("screen_replay_flag"):
            claude = {
                "face_synthetic_probability": 0.0,
                "screen_replay_probability": 1.0,
                "people_visible": 1,
                "stress_signals": False,
                "coercion_signals": False,
                "artifacts_found": ["screen replay confirmed by optical analysis"],
                "verdict": "BLOCK",
            }
            _log("  skipped (screen replay already confirmed by Layer 1)")
        else:
            claude = claude_vision.analyze(image_bytes)
            _log(f"  synthetic_prob={claude.get('face_synthetic_probability', 0):.2f}  "
                 f"screen_replay_prob={claude.get('screen_replay_probability', 0):.2f}  "
                 f"people={claude.get('people_visible', 1)}  "
                 f"stress={claude.get('stress_signals')}  "
                 f"coercion={claude.get('coercion_signals')}  "
                 f"verdict={claude.get('verdict')}")
            if claude.get("artifacts_found"):
                _log(f"  artifacts: {claude['artifacts_found']}")
    except Exception as exc:
        claude = {
            "face_synthetic_probability": 0.0, "screen_replay_probability": 0.0,
            "people_visible": 1, "stress_signals": False, "coercion_signals": False,
            "artifacts_found": [], "verdict": "PASS", "error": str(exc),
        }
        _log(f"  EXCEPTION: {exc}")

    # ── Signals + risk score ──────────────────────────────────────────────────
    _log("Risk Engine → computing score…")
    amount = 0.0
    m = re.search(r"([0-9]+(?:\.[0-9]{1,2})?)", text)
    if m:
        try:
            amount = float(m.group(1))
        except ValueError:
            pass

    signals = {
        "screen_replay_detected": (
            screen.get("screen_replay_flag", False)
            or claude.get("screen_replay_probability", 0.0) > 0.7
        ),
        "face_synthetic":    claude.get("face_synthetic_probability", 0.0) > 0.6,
        "face_mismatch":     user_is_enrolled and not face_match.get("matched", False),
        "low_image_quality": not face_quality.get("quality_ok", True),
        "multiple_people":   claude.get("people_visible", 1) > 1,
        "coercion_signals":  claude.get("coercion_signals", False),
        "stress_signals":    claude.get("stress_signals", False),
        "new_recipient":     False,
        "amount_over_500":   amount > 500,
        "amount_over_1000":  amount > 1000,
    }

    active = [k for k, v in signals.items() if v]
    _log(f"  active signals: {active if active else ['(none)']}")

    try:
        result = risk_engine.compute(signals)
    except Exception as exc:
        result = {
            "risk_score": 0.0, "recommendation": "ALLOW",
            "reason": f"Risk engine error: {exc}", "signals": signals,
        }

    _log(f"  SCORE={result['risk_score']:.3f}  RECOMMENDATION={result['recommendation']}")
    _log(f"  REASON: {result['reason']}")
    _log(f"  frame saved → {frame_path}")
    _log("=" * 60)

    result["details"] = {
        "moire":        {k: v for k, v in screen.items() if k != "error"},
        "face_quality": face_quality,
        "face_match":   {k: face_match.get(k) for k in ("matched", "similarity", "method") if k in face_match},
        "claude":       {k: claude.get(k) for k in (
                            "face_synthetic_probability", "screen_replay_probability",
                            "verdict", "artifacts_found",
                        )},
        "frame_path":   str(frame_path),
    }
    return result


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "bedrock_model": os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-opus-4-7"),
        "s3_bucket": os.environ.get("AWS_S3_BUCKET", "(not set)"),
        "bunq_key_set": bool(os.environ.get("BUNQ_API_KEY")),
    }


# ── Voice endpoint (audio → full pipeline) ────────────────────────────────────

@app.post("/voice")
async def voice_endpoint(audio: UploadFile = File(...)):
    """
    Accept a voice recording (WebM, OGG, MP3, WAV, FLAC) and run the full pipeline:
    Amazon Transcribe → Amazon Bedrock text model → bunq API → natural language reply.
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
    session_id: Optional[str] = None


@app.post("/query")
def query_endpoint(body: QueryRequest):
    """
    Accept a text query and run the Bedrock + bunq pipeline (STT step skipped).
    Use this when the client already has a transcript (e.g. from Web Speech API).
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty query.")
    try:
        result = voice_pipeline.run_text(body.text, body.session_id)
        return {"response": result, "status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Enroll endpoint (image → Rekognition face enrollment) ────────────────────

@app.post("/enroll/{user_id}")
async def enroll_endpoint(user_id: str, image: UploadFile = File(...)):
    """Enroll a face for fraud detection. Call once per user with a clear face photo."""
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image.")
    try:
        from detection.rekognition import enroll_face
        result = enroll_face(user_id, image_bytes)
        return {"status": "enrolled", **result}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Query-with-frame endpoint (text + camera frame → fraud check → bunq) ─────

@app.post("/query-with-frame")
async def query_with_frame_endpoint(
    text: str = Form(...),
    session_id: Optional[str] = Form(None),
    frame: Optional[UploadFile] = File(None),
):
    """
    Text query + optional camera JPEG frame.
    For payment intents, runs fraud analysis before executing via bunq.
    Returns risk result alongside the bunq response.
    """
    if not text.strip():
        raise HTTPException(status_code=400, detail="Empty query.")

    risk_result = None

    if _is_payment_intent(text):
        # Require a camera frame for all payment intents.
        # If frame is missing or empty, hold the transaction — cannot verify identity.
        if frame is None:
            return {
                "response": (
                    "Transaction held for security review. "
                    "Camera access is required to verify your identity before sending money. "
                    "Please allow camera access and try again."
                ),
                "status": "held",
                "risk": {
                    "risk_score": 0.5,
                    "recommendation": "HOLD",
                    "reason": "No camera frame provided — identity cannot be verified",
                    "signals": {},
                },
            }

        image_bytes = await frame.read()
        if not image_bytes:
            return {
                "response": (
                    "Transaction held for security review. "
                    "Camera capture failed — identity cannot be verified. "
                    "Please try again with camera access enabled."
                ),
                "status": "held",
                "risk": {
                    "risk_score": 0.5,
                    "recommendation": "HOLD",
                    "reason": "Empty camera frame — identity cannot be verified",
                    "signals": {},
                },
            }

        loop = asyncio.get_event_loop()
        risk_result = await loop.run_in_executor(
            None, _run_fraud_analysis, image_bytes, text
        )
        if session_id:
            _risk_store[session_id] = risk_result

        rec = risk_result.get("recommendation", "ALLOW")
        signals = risk_result.get("signals", {})

        # Face mismatch is checked first — always block with a specific message.
        if signals.get("face_mismatch", False):
            return {
                "response": (
                    "Transaction blocked: No face ID match. "
                    "The face detected does not match the enrolled account holder. "
                    "Please retry as the registered account holder."
                ),
                "status": "blocked",
                "risk": risk_result,
            }

        if rec == "BLOCK":
            reason = risk_result.get("reason", "Suspicious activity detected.")
            return {
                "response": f"Transaction blocked for your security. {reason}",
                "status": "blocked",
                "risk": risk_result,
            }

        if rec == "HOLD":
            _pending_payments[session_id or "anon"] = {
                "text": text,
                "risk": risk_result,
            }
            return {
                "response": (
                    "This transaction has been placed on a 24-hour safety hold. "
                    "Our security team will review it before processing. "
                    "You will receive a notification once it is cleared."
                ),
                "status": "held",
                "risk": risk_result,
            }

    try:
        result = voice_pipeline.run_text(text, session_id)
        return {"response": result, "status": "ok", "risk": risk_result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Risk endpoint (last fraud analysis result for a session) ─────────────────

@app.get("/risk/{session_id}")
def risk_endpoint(session_id: str):
    """Return the last fraud analysis result stored for this session."""
    if session_id not in _risk_store:
        return {
            "risk_score": None,
            "recommendation": None,
            "reason": "No analysis available for this session.",
        }
    return _risk_store[session_id]


# ── Debug endpoint (last captured frame + risk result) ───────────────────────

@app.get("/debug/frames")
def debug_frames():
    """List all captured frames with metadata."""
    frames = sorted(DEBUG_DIR.glob("frame_*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "filename": f.name,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "captured_at": datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%H:%M:%S"),
        }
        for f in frames[:20]
    ]


@app.get("/debug/frame/{filename}")
def debug_frame(filename: str):
    """Return a captured frame as a base64 JPEG for display in browser."""
    from fastapi.responses import HTMLResponse
    path = DEBUG_DIR / filename
    if not path.exists() or not path.name.startswith("frame_"):
        raise HTTPException(status_code=404, detail="Frame not found")
    b64 = _b64.b64encode(path.read_bytes()).decode()
    risk_html = ""
    # find matching risk result if any
    for sid, r in _risk_store.items():
        if r.get("details", {}).get("frame_path", "").endswith(filename):
            score = r.get("risk_score", "?")
            rec = r.get("recommendation", "?")
            reason = r.get("reason", "")
            color = {"ALLOW": "#22c55e", "CHALLENGE": "#eab308", "HOLD": "#f97316",
                     "REVIEW": "#ef4444", "BLOCK": "#dc2626"}.get(rec, "#888")
            risk_html = (
                f'<div style="font-family:monospace;margin-top:12px;padding:12px;'
                f'background:#111;border-radius:8px;border:2px solid {color}">'
                f'<b style="color:{color}">{rec}</b> &nbsp; score={score} &nbsp; {reason}</div>'
            )
            break
    html = (
        f'<html><body style="background:#000;margin:0;text-align:center">'
        f'<img src="data:image/jpeg;base64,{b64}" style="max-width:100%;max-height:80vh">'
        f'{risk_html}'
        f'<p style="color:#666;font-family:monospace">{filename}</p>'
        f'</body></html>'
    )
    return HTMLResponse(html)


@app.get("/debug/last")
def debug_last():
    """Redirect browser to the most recent captured frame."""
    from fastapi.responses import RedirectResponse
    frames = sorted(DEBUG_DIR.glob("frame_*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not frames:
        raise HTTPException(status_code=404, detail="No frames captured yet")
    return RedirectResponse(f"/debug/frame/{frames[0].name}")


# ── Enrolled reference image endpoint ────────────────────────────────────────

@app.get("/debug/enrolled/{user_id}")
def debug_enrolled(user_id: str):
    """Return the enrolled reference image and metadata for a user."""
    from detection.rekognition import load_enrolled
    enrolled = load_enrolled()
    if user_id not in enrolled:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not enrolled")
    b64 = enrolled[user_id].get("enrolled_image_b64")
    if not b64:
        raise HTTPException(status_code=404, detail="No reference image stored — user enrolled via Rekognition only")
    return {
        "user_id": user_id,
        "image_b64": b64,
        "method": enrolled[user_id].get("method", "unknown"),
        "face_id": enrolled[user_id].get("face_id"),
    }
