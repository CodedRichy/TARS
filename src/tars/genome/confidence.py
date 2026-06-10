from __future__ import annotations

DECAY_HALF_LIFE_DAYS = 90.0
DEPRECATION_THRESHOLD = 0.45
PROMOTION_MIN_CONFIDENCE = 0.70
PROMOTION_MIN_EVIDENCE = 3.0
PROMOTION_MIN_FRESH = 2


def compute_confidence(supporting: float, contradicting: float) -> float:
    alpha = supporting + 1
    beta = contradicting + 1
    return alpha / (alpha + beta)


def apply_decay(
    supporting: float,
    contradicting: float,
    days_elapsed: float,
    half_life: float = DECAY_HALF_LIFE_DAYS,
) -> tuple[float, float]:
    if days_elapsed <= 0:
        return supporting, contradicting
    factor = 0.5 ** (days_elapsed / half_life)
    return supporting * factor, contradicting * factor


def decayed_confidence(
    supporting: float,
    contradicting: float,
    days_elapsed: float,
    half_life: float = DECAY_HALF_LIFE_DAYS,
) -> float:
    s, c = apply_decay(supporting, contradicting, days_elapsed, half_life)
    return compute_confidence(s, c)


def evidence_strength(supporting: float, contradicting: float) -> str:
    total = supporting + contradicting
    if total < 3:
        return "weak"
    if total < 10:
        return "moderate"
    if total < 30:
        return "strong"
    return "robust"


def should_deprecate(confidence: float) -> bool:
    return confidence < DEPRECATION_THRESHOLD
