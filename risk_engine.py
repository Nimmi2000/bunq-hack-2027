"""
Risk scoring engine for transaction fraud detection.

Computes a weighted 0.0–1.0 risk score from boolean signals and maps it
to a 5-tier recommendation: ALLOW / CHALLENGE / HOLD / REVIEW / BLOCK.

Hard-block override: 2+ hard-block signals, or 1 hard-block signal with
score >= 0.65, escalates directly to BLOCK regardless of total score.
"""

WEIGHTS: dict[str, float] = {
    "screen_replay_detected": 0.01,
    "face_synthetic":         0.60,
    "face_mismatch":          0.70,
    "coercion_signals":       0.60,
    "multiple_people":        0.35,
    "stress_signals":         0.25,
    "low_image_quality":      0.20,
    "new_recipient":          0.25,
    "amount_over_1000":       0.35,
    "amount_over_500":        0.20,
}

HARD_BLOCK: set[str] = {"coercion_signals", "screen_replay_detected", "face_mismatch"}

# (upper_exclusive_threshold, action)
_TIERS: list[tuple[float, str]] = [
    (0.25, "ALLOW"),
    (0.50, "CHALLENGE"),
    (0.70, "HOLD"),
    (0.85, "REVIEW"),
    (1.01, "BLOCK"),
]

_REASON_LABELS: dict[str, str] = {
    "screen_replay_detected": "Screen replay attack detected",
    "face_synthetic":         "Synthetic face / deepfake detected",
    "face_mismatch":          "No face ID match",
    "coercion_signals":       "Possible coercion detected",
    "multiple_people":        "Multiple people visible",
    "stress_signals":         "Stress signals detected",
    "low_image_quality":      "Low image quality",
    "amount_over_1000":       "High-value transaction (>€1000)",
    "amount_over_500":        "Elevated transaction amount (>€500)",
    "new_recipient":          "New / unknown recipient",
}


def compute(signals: dict) -> dict:
    """
    signals: dict[str, bool] — each key maps to True if the signal is active.
    Returns: {risk_score, recommendation, reason, signals}
    """
    active = {k for k, v in signals.items() if v}
    raw = sum(WEIGHTS.get(k, 0.0) for k in active)
    score = min(1.0, raw)

    hard_hits = active & HARD_BLOCK
    if len(hard_hits) >= 2 or (len(hard_hits) == 1 and score >= 0.65):
        recommendation = "BLOCK"
    else:
        recommendation = next(action for threshold, action in _TIERS if score < threshold)

    reasons = [_REASON_LABELS[k] for k in _REASON_LABELS if k in active]

    return {
        "risk_score": round(score, 3),
        "recommendation": recommendation,
        "reason": "; ".join(reasons) if reasons else "No risk signals detected",
        "signals": {k: bool(v) for k, v in signals.items()},
    }
