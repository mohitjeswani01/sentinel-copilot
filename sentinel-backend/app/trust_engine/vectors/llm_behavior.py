"""
Sentinel Copilot — Trust Vector: LLM Behavior.

Evaluates LLM-related telemetry for a container/service by querying
SigNoz via the MCP client for traces with LLM-related span names
(e.g. ``llm.chat.completion``, ``gen_ai.*``).

Weight in overall Trust Score: **20 %**

Scoring logic:
  - No LLM telemetry detected → **100** (neutral — not applicable).
  - LLM telemetry found:
    * Base score = 80 (LLM activity detected, mild inherent risk).
    * Penalty: high estimated cost-per-hour (> $5/hr threshold) → −30.
      ($5/hr chosen as illustrative demo threshold; in production this
      would be configurable per org.)
    * Penalty: high average latency (> 5000ms) → −20.
      (5s per LLM call suggests complex or recursive agent loops
      that may indicate autonomous, unsanctioned AI reasoning.)
    * Bonus: low token usage (well-controlled agent) → +10.

The vector is designed to NEVER penalise containers that aren't LLM
agents — only containers with actual LLM telemetry are scored.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.observability.mcp_client import MCPClientError, SentinelMCPClient

logger = logging.getLogger(__name__)

# ── Threshold constants ──────────────────────────────────────────────────────
# $5/hr chosen as an illustrative demo threshold for hackathon demo.
# In production this would be a configurable per-org budget limit.
COST_PER_HOUR_THRESHOLD = 5.0

# 5000ms average LLM call latency — suggests complex/recursive agent chains.
LATENCY_MS_THRESHOLD = 5000.0

# Span names that indicate LLM activity (OpenTelemetry Semantic Conventions
# for GenAI, plus common patterns from LangChain/OpenAI/Google instrumentation).
LLM_SPAN_PATTERNS = [
    "llm.chat.completion",
    "gen_ai.",
    "openai.",
    "gemini.",
    "langchain.",
    "chat_completion",
    "llm_call",
]


def _extract_llm_stats(raw_result: dict[str, Any]) -> dict[str, Any] | None:
    """Parse LLM telemetry from a signoz_search_traces MCP response.

    Returns a stats dict with ``span_count``, ``avg_latency_ms``,
    ``total_tokens`` (if available), or ``None`` if no LLM spans found.
    """
    content = raw_result.get("content", [])
    if not content:
        return None

    text = content[0].get("text", "") if content else ""
    try:
        data = json.loads(text)
    except (ValueError, KeyError):
        return None

    if data.get("status") != "success":
        return None

    results = data.get("data", {}).get("data", {}).get("results", [])
    if not results:
        return None

    span_count = 0
    total_duration_ns = 0
    total_tokens = 0

    for result_set in results:
        rows = result_set.get("rows") or []
        for row in rows:
            name = row.get("name", "") or row.get("operationName", "")
            name_lower = name.lower()

            # Check if this span is LLM-related
            is_llm = any(pattern in name_lower for pattern in LLM_SPAN_PATTERNS)
            if not is_llm:
                continue

            span_count += 1
            dur_ns = row.get("durationNano", 0)
            total_duration_ns += dur_ns

            # Try to extract token counts from span attributes
            # (common OTel GenAI semantic convention attributes)
            for key in ("gen_ai.usage.total_tokens", "llm.token_count.total",
                        "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"):
                val = row.get(key)
                if val:
                    try:
                        total_tokens += int(val)
                    except (ValueError, TypeError):
                        pass

    if span_count == 0:
        return None

    avg_latency_ms = (total_duration_ns / span_count / 1_000_000) if span_count else 0.0

    return {
        "span_count": span_count,
        "avg_latency_ms": avg_latency_ms,
        "total_tokens": total_tokens,
    }


async def score_llm_behavior(
    container_name: str,
    mcp_client: SentinelMCPClient,
) -> tuple[float, str]:
    """Score the LLM behavior vector for a single container.

    Queries SigNoz via MCP for traces with LLM-related span names.
    If no LLM telemetry exists, returns a neutral default score (100).

    Args:
        container_name: Container/service name to look up in SigNoz.
        mcp_client: An already-initialized ``SentinelMCPClient``.

    Returns:
        A ``(score, reasoning)`` tuple where *score* is 0–100.
    """
    try:
        raw = await mcp_client.search_traces(
            service_name=container_name,
            limit=20,
            time_range="1h",
        )
    except MCPClientError as exc:
        logger.debug(
            "LLM behavior: trace search for '%s' failed: %s — returning neutral",
            container_name,
            exc,
        )
        return 100.0, f"Trace search unavailable ({exc}) — LLM behavior not scored"

    stats = _extract_llm_stats(raw)

    if stats is None:
        return 100.0, "No LLM activity detected — not applicable"

    # LLM activity detected — start scoring
    score = 80.0
    reasons: list[str] = []

    span_count = stats["span_count"]
    avg_latency = stats["avg_latency_ms"]
    total_tokens = stats["total_tokens"]

    reasons.append(f"LLM activity detected: {span_count} span(s)")

    # Rough cost estimate: ~$0.002 per 1K tokens (GPT-4-class pricing).
    # This is a very rough proxy — real cost tracking uses actual provider bills.
    estimated_cost_per_hour = (total_tokens / 1000.0) * 0.002 * (3600_000 / max(avg_latency, 1))

    # ── Penalty: high cost ───────────────────────────────────────────────
    if estimated_cost_per_hour > COST_PER_HOUR_THRESHOLD:
        score -= 30
        reasons.append(
            f"Estimated cost ${estimated_cost_per_hour:.2f}/hr > "
            f"${COST_PER_HOUR_THRESHOLD}/hr threshold (−30)"
        )
    elif total_tokens > 0:
        reasons.append(
            f"Estimated cost ${estimated_cost_per_hour:.2f}/hr within budget (+0)"
        )

    # ── Penalty: high latency ────────────────────────────────────────────
    if avg_latency > LATENCY_MS_THRESHOLD:
        score -= 20
        reasons.append(
            f"Avg LLM latency {avg_latency:.0f}ms > "
            f"{LATENCY_MS_THRESHOLD:.0f}ms threshold (−20) — "
            "may indicate recursive agent chains"
        )
    else:
        reasons.append(f"Avg LLM latency {avg_latency:.0f}ms (acceptable)")

    # ── Bonus: low token usage ───────────────────────────────────────────
    if 0 < total_tokens < 500:
        score += 10
        reasons.append(f"Low token usage ({total_tokens} total) — well-controlled (+10)")

    score = max(0.0, min(100.0, score))
    reasoning = "; ".join(reasons)
    logger.debug("LLM behavior score=%.1f for '%s': %s", score, container_name, reasoning)

    return score, reasoning
