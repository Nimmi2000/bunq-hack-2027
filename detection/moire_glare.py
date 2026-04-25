"""
Screen replay detection via optical analysis.

Detects: moiré interference patterns (FFT), screen glare, and device bezels.
Returns probability scores without storing any image data.
"""

import io
import cv2
import numpy as np
from PIL import Image


def analyze(image_bytes: bytes) -> dict:
    pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = np.array(pil_img)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    moire = _moire_score(gray)
    glare = _glare_score(gray)
    bezel = _bezel_score(gray)

    screen_replay_flag = (
        moire["peak_ratio"] > 8.5
        or glare["glare_detected"]
        or bezel["bezel_detected"]
    )

    raw_score = (
        min(moire["peak_ratio"] / 20.0, 1.0) * 0.5
        + (0.3 if glare["glare_detected"] else 0.0)
        + (0.2 if bezel["bezel_detected"] else 0.0)
    )

    return {
        "screen_probability": round(min(1.0, raw_score), 3),
        "moire_peak_ratio": round(moire["peak_ratio"], 2),
        "glare_regions": glare["glare_regions"],
        "dark_corners": bezel["dark_corners"],
        "screen_replay_flag": screen_replay_flag,
    }


def _moire_score(gray: np.ndarray) -> dict:
    f = np.fft.fft2(gray.astype(np.float32))
    fshift = np.fft.fftshift(f)
    magnitude = np.abs(fshift)

    h, w = gray.shape
    cy, cx = h // 2, w // 2
    Y, X = np.ogrid[:h, :w]
    outer_mask = (X - cx) ** 2 + (Y - cy) ** 2 > 30 ** 2

    outer = magnitude[outer_mask]
    peak_ratio = float(outer.max() / (outer.mean() + 1e-6))
    return {"peak_ratio": peak_ratio}


def _glare_score(gray: np.ndarray) -> dict:
    _, bright = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY)
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(bright, connectivity=8)

    glare_regions = sum(
        1 for i in range(1, num_labels) if stats[i, cv2.CC_STAT_AREA] > 400
    )
    return {"glare_regions": glare_regions, "glare_detected": glare_regions > 0}


def _bezel_score(gray: np.ndarray) -> dict:
    h, w = gray.shape
    patch = max(20, h // 8)

    corners = [
        gray[:patch, :patch],
        gray[:patch, w - patch:],
        gray[h - patch:, :patch],
        gray[h - patch:, w - patch:],
    ]

    dark_corners = sum(1 for c in corners if c.mean() < 35 and c.std() < 12)
    return {"dark_corners": dark_corners, "bezel_detected": dark_corners >= 2}
