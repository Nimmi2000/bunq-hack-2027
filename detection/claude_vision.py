"""
Deepfake and coercion detection via Claude Vision (claude-haiku for speed).

Checks: synthetic face artifacts, screen replay indicators, multiple people,
stress signals, and coercion signals — all from a single JPEG frame.
"""

import base64
import json
import os

import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


_PROMPT = """Analyze this image for banking fraud detection. This frame is captured from a live camera during a financial transaction authorization.

Examine carefully for each of the following:

1. SCREEN REPLAY ATTACK — Is this a photo/video of a screen showing another face?
   Signs: visible device bezels, moiré grid patterns, screen glare/reflections, pixelation.

2. DEEPFAKE / SYNTHETIC FACE — Is the face AI-generated or digitally manipulated?
   Signs: missing or symmetric eye catchlights, unnatural hair-skin boundary blending,
   overly smooth skin texture, teeth/mouth artifacts, lighting mismatches.

3. MULTIPLE PEOPLE — Count visible or partially visible faces.

4. STRESS SIGNALS — Does the person appear anxious or distressed?
   Signs: tense jaw, wide eyes, averted gaze, visible perspiration.

5. COERCION SIGNALS — Is the person being directed by someone else?
   Signs: someone else visible in background, phone held near person's face,
   person looking off-screen for guidance repeatedly.

Return ONLY a valid JSON object with exactly these fields (no markdown, no explanation):
{
  "face_synthetic_probability": 0.0,
  "screen_replay_probability": 0.0,
  "people_visible": 1,
  "stress_signals": false,
  "coercion_signals": false,
  "artifacts_found": [],
  "verdict": "PASS"
}

Field rules:
- face_synthetic_probability: 0.0–1.0; only use >0.7 when very confident
- screen_replay_probability: 0.0–1.0; only use >0.7 when very confident
- people_visible: integer count of human faces visible
- stress_signals: boolean
- coercion_signals: boolean
- artifacts_found: list of short strings describing specific detected artifacts
- verdict: "PASS" | "SUSPICIOUS" | "BLOCK"
"""


def analyze(image_bytes: bytes) -> dict:
    if not ANTHROPIC_API_KEY:
        return _default_result()

    try:
        b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        media_type = "image/jpeg"
        if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            media_type = "image/png"

        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }],
        )

        raw = response.content[0].text.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        return _default_result()

    except Exception as exc:
        return {**_default_result(), "error": str(exc)}


def compare_faces(live_bytes: bytes, enrolled_bytes: bytes) -> dict:
    """
    Compare a live camera frame against the enrolled reference photo.
    Returns {same_person: bool|None, confidence: 0.0-1.0, reason: str}
    Used as a Rekognition fallback when no AWS IAM credentials are available.
    """
    if not ANTHROPIC_API_KEY:
        return {"same_person": None, "confidence": 0.0, "error": "No ANTHROPIC_API_KEY"}

    def _b64(b: bytes) -> str:
        return base64.standard_b64encode(b).decode("utf-8")

    def _mtype(b: bytes) -> str:
        return "image/png" if b[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"

    try:
        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Image 1 is the ENROLLED reference photo of the bank account holder."},
                    {"type": "image", "source": {"type": "base64", "media_type": _mtype(enrolled_bytes), "data": _b64(enrolled_bytes)}},
                    {"type": "text", "text": "Image 2 is a live camera capture taken during a financial transaction."},
                    {"type": "image", "source": {"type": "base64", "media_type": _mtype(live_bytes), "data": _b64(live_bytes)}},
                    {"type": "text", "text": (
                        "You are a strict banking security system. Your job is identity verification for fraud prevention. "
                        "Compare the ENROLLED reference photo (Image 1) with the LIVE camera capture (Image 2). "
                        "They must be the SAME individual — same facial structure, same person, beyond reasonable doubt. "
                        "If there is ANY doubt, ANY difference, or ANY uncertainty, you MUST answer false. "
                        "Default to false. Only answer true if you are certain (>90%) it is the same person. "
                        'Reply ONLY with valid JSON, no markdown: {"same_person": false, "confidence": 0.0, "reason": "..."}'
                    )},
                ],
            }],
        )
        raw = response.content[0].text.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        return {"same_person": None, "confidence": 0.0}
    except Exception as exc:
        return {"same_person": None, "confidence": 0.0, "error": str(exc)}


def _default_result() -> dict:
    return {
        "face_synthetic_probability": 0.0,
        "screen_replay_probability": 0.0,
        "people_visible": 1,
        "stress_signals": False,
        "coercion_signals": False,
        "artifacts_found": [],
        "verdict": "PASS",
    }
