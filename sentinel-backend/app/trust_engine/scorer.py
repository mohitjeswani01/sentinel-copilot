"""
Sentinel Copilot — Trust Score Aggregator.

Combines individual vector scores into a single weighted Trust Score and
maps it to a human-readable risk tier.

Weight breakdown (5 active vectors):
  * Identity:      25 %
  * Configuration:  25 %
  * Network:        15 %
  * Resources:      15 %
  * LLM Behavior:   20 %  (returns neutral 100 for non-LLM containers,
    so this vector never penalises containers that aren't LLM agents)

Risk tier thresholds:
  * < 40  → CRITICAL
  * < 60  → HIGH RISK
  * < 80  → ELEVATED
  * ≥ 80  → HEALTHY
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Weight configuration ─────────────────────────────────────────────────────
VECTOR_WEIGHTS: dict[str, float] = {
    "identity": 0.25,
    "configuration": 0.25,
    "network": 0.15,
    "resources": 0.15,
    "llm_behavior": 0.20,
}

# ── Risk tier thresholds ─────────────────────────────────────────────────────
_TIER_CRITICAL = 40.0
_TIER_HIGH_RISK = 60.0
_TIER_ELEVATED = 80.0


def _score_to_tier(score: float) -> str:
    """Map a numeric trust score to a risk tier label."""
    if score < _TIER_CRITICAL:
        return "CRITICAL"
    if score < _TIER_HIGH_RISK:
        return "HIGH RISK"
    if score < _TIER_ELEVATED:
        return "ELEVATED"
    return "HEALTHY"


def calculate_trust_score(
    vector_scores: dict[str, float],
) -> tuple[float, str]:
    """Compute the overall Trust Score from individual vector scores.

    Missing vectors are skipped and their weight is redistributed
    proportionally across the remaining vectors, so the final score
    always reflects the available data.

    Args:
        vector_scores: Mapping of vector name (``identity``,
            ``configuration``, ``network``, ``resources``) to its
            individual score (0–100).

    Returns:
        A ``(trust_score, risk_tier)`` tuple where *trust_score* is
        0–100 and *risk_tier* is one of ``CRITICAL``, ``HIGH RISK``,
        ``ELEVATED``, or ``HEALTHY``.
    """
    weighted_sum = 0.0
    total_weight = 0.0

    for vector_name, weight in VECTOR_WEIGHTS.items():
        score = vector_scores.get(vector_name)
        if score is not None:
            weighted_sum += score * weight
            total_weight += weight

    if total_weight <= 0:
        logger.warning("No vector scores provided — defaulting to 0")
        return 0.0, "CRITICAL"

    # Normalise if some vectors were missing (redistribute weight)
    trust_score = weighted_sum / total_weight
    trust_score = max(0.0, min(100.0, trust_score))

    risk_tier = _score_to_tier(trust_score)

    logger.info(
        "Trust Score=%.1f (%s) — vectors: %s",
        trust_score,
        risk_tier,
        {k: f"{v:.0f}" for k, v in vector_scores.items()},
    )

    return trust_score, risk_tier
