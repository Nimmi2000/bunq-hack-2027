"""Face authentication via a Bedrock vision model (bearer-token, no IAM keys)."""

import base64
import os
import urllib.parse
from pathlib import Path

import requests as _http

REFERENCE_PATH = Path(__file__).parents[2] / "face_reference.jpg"

_REGION   = lambda: os.environ.get("AWS_REGION", "us-east-1")
_API_KEY  = lambda: (
    os.environ.get("FACE_API_KEY", "").strip().strip('"')
    or os.environ.get("AWS_BEDROCK_API_KEY", "").strip().strip('"')
)
_MODEL_ID = lambda: os.environ.get("FACE_MODEL_ID", "amazon.nova-lite-v1:0")


def reference_exists() -> bool:
    return REFERENCE_PATH.exists()


def save_reference(image_bytes: bytes) -> None:
    REFERENCE_PATH.write_bytes(image_bytes)


def verify(live_bytes: bytes) -> tuple[bool, float]:
    """
    Ask a Bedrock vision model whether live_bytes shows the same face as the
    stored reference image. Returns (match, 100.0) on YES, (False, 0.0) on NO.
    """
    if not reference_exists():
        raise RuntimeError("No reference face image configured. Run face setup first.")

    api_key = _API_KEY()
    if not api_key:
        raise EnvironmentError("FACE_API_KEY (or AWS_BEDROCK_API_KEY) is required.")

    ref_b64  = base64.b64encode(REFERENCE_PATH.read_bytes()).decode()
    live_b64 = base64.b64encode(live_bytes).decode()

    endpoint = (
        f"https://bedrock-runtime.{_REGION()}.amazonaws.com"
        f"/model/{urllib.parse.quote(_MODEL_ID(), safe='')}/converse"
    )
    _PROMPT = (
        "You are a strict biometric face-verification security system for a banking app.\n"
        "Image 1 is the REGISTERED REFERENCE face of the authorised account holder.\n"
        "Image 2 is the LIVE CAPTURE from the webcam attempting to perform a banking action.\n\n"
        "Compare every visible facial feature in both images with extreme precision:\n"
        "  • overall face shape and proportions\n"
        "  • eye shape, spacing, and colour\n"
        "  • nose shape and size\n"
        "  • mouth and lip shape\n"
        "  • eyebrow shape and thickness\n"
        "  • jawline and chin\n"
        "  • any distinctive marks, features, or characteristics\n\n"
        "Rules:\n"
        "  • Only reply YES if you are CERTAIN (>95% confidence) that Image 2 shows the EXACT SAME person as Image 1.\n"
        "  • If the person is different, the face is obscured, the image is unclear, or there is ANY doubt, reply NO.\n"
        "  • Do NOT be fooled by similar-looking people, photos of photos, or masks.\n\n"
        "Reply with a single word: YES or NO."
    )

    payload = {
        "messages": [{
            "role": "user",
            "content": [
                {"image": {"format": "jpeg", "source": {"bytes": ref_b64}}},
                {"image": {"format": "jpeg", "source": {"bytes": live_b64}}},
                {"text": _PROMPT},
            ],
        }],
        "inferenceConfig": {"maxTokens": 5, "temperature": 0.0},
    }
    resp = _http.post(
        endpoint,
        json=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()

    content = (
        resp.json()
        .get("output", {})
        .get("message", {})
        .get("content", [])
    )
    # The model must start its answer with YES — anything else (NO, UNSURE, etc.) is a rejection
    answer = "".join(b.get("text", "") for b in content if "text" in b).strip().upper()
    match  = answer.startswith("YES")
    return match, 100.0 if match else 0.0
