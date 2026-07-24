"""
Sentinel Copilot — Trust Vector: Resources.

Evaluates container resource governance:
  - Whether memory limits are set (no limit = OOM risk).
  - Whether CPU limits are set.
  - CPU / memory usage above 80 % (resource abuse indicator).

Weight in overall Trust Score: **20 %**
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _parse_cpu_usage(stats: dict[str, Any]) -> float | None:
    """Calculate CPU usage percentage from Docker stats snapshot.

    Returns a float 0–100, or ``None`` if the stats are missing fields.
    """
    try:
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})

        cpu_delta = (
            cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            - precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
        )
        system_delta = (
            cpu_stats.get("system_cpu_usage", 0)
            - precpu_stats.get("system_cpu_usage", 0)
        )

        if system_delta <= 0 or cpu_delta < 0:
            return None

        num_cpus = cpu_stats.get("online_cpus") or len(
            cpu_stats.get("cpu_usage", {}).get("percpu_usage", [1])
        )
        return (cpu_delta / system_delta) * num_cpus * 100.0
    except (TypeError, KeyError, ZeroDivisionError):
        return None


def _parse_memory_usage(stats: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return ``(usage_bytes, limit_bytes)`` from Docker stats.

    Returns ``(None, None)`` if the data is missing.
    """
    try:
        mem = stats.get("memory_stats", {})
        usage = mem.get("usage")
        limit = mem.get("limit")
        return usage, limit
    except (TypeError, KeyError):
        return None, None


def score_resources(
    container_stats: dict[str, Any],
    container_inspect: dict[str, Any],
) -> tuple[float, str]:
    """Score the resources vector for a single container.

    Scoring logic (ported from archestra-sentinel):

    Base score starts at **100**.

    +----------------+--------------------------------------------+---------+
    | Check          | Condition                                  | Effect  |
    +----------------+--------------------------------------------+---------+
    | No mem limit   | ``HostConfig.Memory`` == 0 (unlimited)     | −20 pts |
    | No CPU limit   | ``HostConfig.NanoCpus`` == 0 (unlimited)   | −15 pts |
    | CPU usage >80% | Computed from stats snapshot               | −20 pts |
    | Mem usage >80% | Computed from stats snapshot               | −20 pts |
    +----------------+--------------------------------------------+---------+

    Final score is clamped to [0, 100].

    Args:
        container_stats: Docker stats snapshot (non-streaming).
        container_inspect: Full ``docker inspect`` dict.

    Returns:
        A ``(score, reasoning)`` tuple.
    """
    score = 100.0
    reasons: list[str] = []

    host_config = container_inspect.get("HostConfig", {})

    # ── Check 1: Memory limit ────────────────────────────────────────────
    memory_limit = host_config.get("Memory", 0)
    if not memory_limit or memory_limit == 0:
        score -= 20
        reasons.append("No memory limit set (−20) — OOM risk")
    else:
        reasons.append(f"Memory limit set to {memory_limit // (1024 * 1024)}MB (+0)")

    # ── Check 2: CPU limit ───────────────────────────────────────────────
    nano_cpus = host_config.get("NanoCpus", 0)
    cpu_period = host_config.get("CpuPeriod", 0)
    cpu_quota = host_config.get("CpuQuota", 0)

    has_cpu_limit = (nano_cpus and nano_cpus > 0) or (cpu_quota and cpu_quota > 0)

    if not has_cpu_limit:
        score -= 15
        reasons.append("No CPU limit set (−15)")
    else:
        reasons.append("CPU limit configured (+0)")

    # ── Check 3: CPU usage > 80 % ────────────────────────────────────────
    cpu_pct = _parse_cpu_usage(container_stats)
    if cpu_pct is not None:
        if cpu_pct > 80.0:
            score -= 20
            reasons.append(f"CPU usage {cpu_pct:.1f}% > 80% threshold (−20)")
        else:
            reasons.append(f"CPU usage {cpu_pct:.1f}% (within limits)")
    else:
        reasons.append("CPU usage data unavailable")

    # ── Check 4: Memory usage > 80 % ────────────────────────────────────
    mem_usage, mem_limit = _parse_memory_usage(container_stats)
    if mem_usage is not None and mem_limit is not None and mem_limit > 0:
        mem_pct = (mem_usage / mem_limit) * 100.0
        if mem_pct > 80.0:
            score -= 20
            reasons.append(f"Memory usage {mem_pct:.1f}% > 80% threshold (−20)")
        else:
            reasons.append(f"Memory usage {mem_pct:.1f}% (within limits)")
    else:
        reasons.append("Memory usage data unavailable")

    score = max(0.0, min(100.0, score))

    reasoning = "; ".join(reasons)
    logger.debug("Resources score=%.1f: %s", score, reasoning)

    return score, reasoning
