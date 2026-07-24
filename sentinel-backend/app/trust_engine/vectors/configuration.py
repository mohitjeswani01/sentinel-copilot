"""
Sentinel Copilot — Trust Vector: Configuration.

Evaluates container runtime configuration for security posture:
  - Running as root user (penalty)
  - Privileged mode enabled (major penalty)
  - Read-only root filesystem (bonus if enabled)

Weight in overall Trust Score: **30 %**
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def score_configuration(container_inspect: dict[str, Any]) -> tuple[float, str]:
    """Score the configuration vector for a single container.

    Scoring logic (ported from archestra-sentinel):

    +--------+--------------------------------------------------+----------+
    | Check  | Condition                                        | Effect   |
    +--------+--------------------------------------------------+----------+
    | Root   | Container runs as root (UID 0 or User="")       | −25 pts  |
    | Priv   | ``HostConfig.Privileged`` is ``True``            | −40 pts  |
    | RO FS  | ``HostConfig.ReadonlyRootfs`` is ``True``        | +15 pts  |
    +--------+--------------------------------------------------+----------+

    Base score starts at **100** and is reduced by penalties / increased
    by bonuses, then clamped to [0, 100].

    Args:
        container_inspect: Full ``docker inspect`` dict for the container.

    Returns:
        A ``(score, reasoning)`` tuple.
    """
    score = 100.0
    reasons: list[str] = []

    config = container_inspect.get("Config", {})
    host_config = container_inspect.get("HostConfig", {})

    # ── Check 1: Running as root ─────────────────────────────────────────
    user = config.get("User", "")
    if not user or user == "0" or user == "root":
        score -= 25
        reasons.append("Running as root user (−25)")
    else:
        reasons.append(f"Non-root user '{user}' (+0, baseline)")

    # ── Check 2: Privileged mode ─────────────────────────────────────────
    privileged = host_config.get("Privileged", False)
    if privileged:
        score -= 40
        reasons.append("Privileged mode ENABLED (−40) — full host access")
    else:
        reasons.append("Privileged mode disabled (+0, baseline)")

    # ── Check 3: Read-only root filesystem ───────────────────────────────
    readonly_rootfs = host_config.get("ReadonlyRootfs", False)
    if readonly_rootfs:
        score += 15
        reasons.append("Read-only rootfs enabled (+15)")
    else:
        reasons.append("Read-only rootfs NOT set (−0, no bonus)")

    # Clamp to [0, 100]
    score = max(0.0, min(100.0, score))

    reasoning = "; ".join(reasons)
    logger.debug("Configuration score=%.1f: %s", score, reasoning)

    return score, reasoning
