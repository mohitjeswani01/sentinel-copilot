"""
Sentinel Copilot — Background Container Scanner.

Runs as an ``asyncio`` background task tied to the FastAPI application
lifespan.  Every ``settings.SCAN_INTERVAL_SECONDS`` it:

1. Lists all running Docker containers via ``docker_bridge``.
2. Inspects and collects stats for each container.
3. Runs the 4 trust-engine vector scorers + the weighted aggregator.
4. Emits the resulting metrics to SigNoz through ``SentinelMetricsEmitter``.

Errors in individual containers are caught and logged — one failing
container never crashes the whole scan loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.core.docker_bridge import (
    get_container_inspect,
    get_container_stats,
    list_running_containers,
)
from app.observability.mcp_client import SentinelMCPClient
from app.observability.metrics_emitter import SentinelMetricsEmitter
from app.trust_engine.scorer import calculate_trust_score
from app.trust_engine.vectors.configuration import score_configuration
from app.trust_engine.vectors.identity import score_identity
from app.trust_engine.vectors.llm_behavior import score_llm_behavior
from app.trust_engine.vectors.network import score_network
from app.trust_engine.vectors.resources import score_resources

# Imported lazily inside the loop to avoid circular imports at module load time.
# We import the function directly here because the loop module itself imports
# background_scanner (for get_container_result), so we must not import at
# top-level to keep the import graph acyclic.
_COPILOT_INVESTIGATE_TIERS = {"CRITICAL", "HIGH RISK"}

logger = logging.getLogger(__name__)

# Module-level emitter singleton — initialised on first ``start_scanner()``
_emitter: SentinelMetricsEmitter | None = None
_scanner_task: asyncio.Task[None] | None = None

# ── In-memory scan results store ─────────────────────────────────────────────
# Keyed by container_id → latest scan result dict.  Updated each scan cycle.
# Accessed by the API routes to serve container data without re-scanning.
_last_scan_results: dict[str, dict[str, Any]] = {}


async def _score_container(
    container_summary: dict[str, Any],
    mcp_client: SentinelMCPClient | None = None,
) -> dict[str, Any] | None:
    """Run all trust vectors on a single container and return results.

    Returns ``None`` if inspection / stats fetching fails for this
    container (the error is logged internally).
    """
    cid = container_summary["id"]
    cname = container_summary.get("name", cid)

    try:
        inspect_data = get_container_inspect(cid)
    except Exception:
        logger.warning("Could not inspect container %s (%s) — skipping", cname, cid)
        return None

    try:
        stats_data = get_container_stats(cid, stream=False)
    except Exception:
        logger.warning(
            "Could not fetch stats for %s (%s) — scoring with empty stats",
            cname,
            cid,
        )
        stats_data = {}

    # ── Run individual vectors ───────────────────────────────────────────
    id_score, id_reason = score_identity(inspect_data)
    cfg_score, cfg_reason = score_configuration(inspect_data)
    net_score, net_reason = score_network(inspect_data)
    res_score, res_reason = score_resources(stats_data, inspect_data)

    if mcp_client is not None:
        try:
            llm_score, llm_reason = await score_llm_behavior(cname, mcp_client)
        except Exception as exc:
            logger.warning("Could not score LLM behavior for %s: %s", cname, exc)
            llm_score, llm_reason = 100.0, f"LLM check error ({exc}) — not applicable"
    else:
        llm_score, llm_reason = 100.0, "No LLM activity detected — not applicable"

    vector_scores: dict[str, float] = {
        "identity": id_score,
        "configuration": cfg_score,
        "network": net_score,
        "resources": res_score,
        "llm_behavior": llm_score,
    }

    trust_score, risk_tier = calculate_trust_score(vector_scores)

    logger.info(
        "Container %s (%s): Trust=%.1f [%s]  id=%.0f cfg=%.0f net=%.0f res=%.0f llm=%.0f",
        cname,
        cid,
        trust_score,
        risk_tier,
        id_score,
        cfg_score,
        net_score,
        res_score,
        llm_score,
    )

    return {
        "container_id": cid,
        "container_name": cname,
        "trust_score": trust_score,
        "risk_tier": risk_tier,
        "vector_scores": vector_scores,
        "vector_reasons": {
            "identity": id_reason,
            "configuration": cfg_reason,
            "network": net_reason,
            "resources": res_reason,
            "llm_behavior": llm_reason,
        },
    }


async def _scan_loop() -> None:
    """Infinite async loop that scans containers at the configured interval."""
    global _emitter  # noqa: PLW0603

    if _emitter is None:
        _emitter = SentinelMetricsEmitter()

    logger.info(
        "Scanner loop started — scanning every %d s",
        settings.SCAN_INTERVAL_SECONDS,
    )

    while True:
        try:
            containers = list_running_containers()
            logger.info("Scan cycle: %d running container(s) found", len(containers))

            mcp_client: SentinelMCPClient | None = None
            try:
                mcp = SentinelMCPClient()
                await mcp.__aenter__()
                await mcp.initialize()
                await mcp.send_initialized_notification()
                mcp_client = mcp
            except Exception as exc:
                logger.debug("MCP client connection unavailable for scanner cycle: %s", exc)

            current_ids: set[str] = set()
            try:
                for container in containers:
                    try:
                        result = await _score_container(container, mcp_client=mcp_client)
                        if result is not None:
                            cid = result["container_id"]
                            current_ids.add(cid)
                            _last_scan_results[cid] = result
                            _emitter.emit_container_trust_metrics(
                                container_id=cid,
                                container_name=result["container_name"],
                                trust_score=result["trust_score"],
                                vector_scores=result["vector_scores"],
                            )
                            # Fire copilot cycle as background task for risky containers.
                            # Import here to avoid circular imports at module level.
                            if result["risk_tier"] in _COPILOT_INVESTIGATE_TIERS:
                                from app.copilot.loop import run_copilot_cycle  # noqa: PLC0415
                                asyncio.get_event_loop().create_task(
                                    run_copilot_cycle(cid),
                                    name=f"copilot-cycle-{cid[:12]}",
                                )
                    except Exception:
                        logger.exception(
                            "Error scoring container %s — continuing",
                            container.get("name", container.get("id", "?")),
                        )
            finally:
                if mcp_client is not None:
                    try:
                        await mcp_client.__aexit__(None, None, None)
                    except Exception:
                        pass

            # Prune containers that are no longer running
            stale = set(_last_scan_results.keys()) - current_ids
            for stale_id in stale:
                del _last_scan_results[stale_id]

        except ConnectionError:
            logger.warning(
                "Docker daemon unreachable — will retry in %d s",
                settings.SCAN_INTERVAL_SECONDS,
            )
        except Exception:
            logger.exception("Unexpected error in scan loop — continuing")

        await asyncio.sleep(settings.SCAN_INTERVAL_SECONDS)


def start_scanner() -> None:
    """Launch the background scanner as an ``asyncio.Task``.

    Safe to call during FastAPI startup (e.g. in a lifespan handler or
    ``@app.on_event("startup")``).  Calling it multiple times is harmless
    — only one task will be created.
    """
    global _scanner_task  # noqa: PLW0603

    if _scanner_task is not None and not _scanner_task.done():
        logger.debug("Scanner task already running — skipping duplicate start")
        return

    loop = asyncio.get_event_loop()
    _scanner_task = loop.create_task(_scan_loop())
    logger.info("Background scanner task created")


# ── Public accessors for API layer ───────────────────────────────────────────

def get_scan_results() -> dict[str, dict[str, Any]]:
    """Return the current in-memory scan results for all containers.

    Returns:
        A dict keyed by ``container_id`` → scan result dict with keys:
        ``container_id``, ``container_name``, ``trust_score``,
        ``risk_tier``, ``vector_scores``, ``vector_reasons``.
    """
    return dict(_last_scan_results)


def get_container_result(container_id: str) -> dict[str, Any] | None:
    """Return the latest scan result for a specific container, or ``None``."""
    return _last_scan_results.get(container_id)
