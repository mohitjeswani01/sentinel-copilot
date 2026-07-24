"""
Sentinel Copilot Backend — Copilot Orchestration Loop.

Coordinates the full autonomous SRE cycle for a single container:

  Scan result → [CRITICAL/HIGH RISK] → Investigate (+ auto-alert inside)
                                     → [CRITICAL only] → Remediate (kill)

Alert trigger ownership: the Investigator is the SINGLE authority for
calling ``create_trust_score_alert()``.  This loop does NOT call
AlertManager directly — it calls ``Investigator.investigate()`` which
handles the alert internally for CRITICAL containers, avoiding duplication.

Meta-observability: every cycle run creates an OTel trace waterfall:
  copilot_cycle → detect → investigate → remediate
visible in SigNoz's Trace Explorer filtered by
``component = sentinel-copilot-brain``.

Design choices:
  - ``run_copilot_cycle()`` is safe to call concurrently for different
    container_ids (each call is fully independent).
  - The background scanner fires it as a fire-and-forget asyncio task so
    the scan loop is never blocked.
  - All errors are caught and logged; a cycle failure never crashes the loop.
"""

from __future__ import annotations

import logging
from typing import Any

from app.copilot.investigator import Investigator
from app.copilot.remediator import Remediator
from app.observability.copilot_tracer import trace_copilot_cycle, trace_copilot_step
from app.scanner.background_scanner import get_container_result

logger = logging.getLogger(__name__)

# Tiers that warrant a full investigation pass
_INVESTIGATE_TIERS = {"CRITICAL", "HIGH RISK"}

# Only this tier triggers autonomous kill
_KILL_TIER = "CRITICAL"


async def run_copilot_cycle(container_id: str) -> dict[str, Any]:
    """Execute one full autonomous SRE cycle for ``container_id``.

    Steps (each is conditional and gated on the previous):
    1. Fetch latest scan result (fast, in-memory).
    2. CRITICAL or HIGH RISK → run Investigator (logs, traces, alert if CRITICAL).
    3. CRITICAL only → run Remediator (autonomous kill).

    Each step is wrapped in an OTel span for meta-observability.

    Returns:
        A summary dict describing what happened at each step, suitable for
        API responses and live demo narration.
    """
    summary: dict[str, Any] = {
        "container_id": container_id,
        "steps_executed": [],
        "final_action": "none",
    }

    # ── Step 1: Fetch scan result ─────────────────────────────────────────
    scan_result = get_container_result(container_id)
    if scan_result is None:
        summary["error"] = (
            f"Container '{container_id}' not found in scan store. "
            "Run a scan cycle first."
        )
        logger.warning("Copilot cycle: no scan data for %s", container_id[:12])
        return summary

    risk_tier = scan_result["risk_tier"]
    trust_score = scan_result["trust_score"]
    container_name = scan_result["container_name"]

    summary["container_name"] = container_name
    summary["trust_score"] = trust_score
    summary["risk_tier"] = risk_tier

    logger.info(
        "Copilot cycle starting: %s (%s) trust=%.1f [%s]",
        container_name,
        container_id[:12],
        trust_score,
        risk_tier,
    )

    # ── Wrap entire cycle in a parent OTel span ───────────────────────────
    with trace_copilot_cycle(
        container_id=container_id,
        container_name=container_name,
        trust_score=trust_score,
        risk_tier=risk_tier,
    ) as _parent_span:

        # ── Step 1b: Detect (record scan result into span) ────────────────
        with trace_copilot_step(
            "detect",
            attributes={
                "container_id": container_id,
                "container_name": container_name,
                "trust_score": trust_score,
                "risk_tier": risk_tier,
            },
        ) as detect_span:
            detect_span.add_event(
                "scan_result_fetched",
                attributes={"vector_scores": str(scan_result["vector_scores"])},
            )

        # ── Step 2: Investigate (CRITICAL + HIGH RISK) ────────────────────
        investigation_result = None
        if risk_tier in _INVESTIGATE_TIERS:
            summary["steps_executed"].append("investigate")
            with trace_copilot_step(
                "investigate",
                attributes={
                    "container_id": container_id,
                    "container_name": container_name,
                    "trust_score": trust_score,
                    "risk_tier": risk_tier,
                },
            ) as inv_span:
                try:
                    async with Investigator() as inv:
                        investigation_result = await inv.investigate(
                            container_id=scan_result["container_id"],
                            container_name=container_name,
                            trust_score=trust_score,
                            vector_scores=scan_result["vector_scores"],
                            vector_reasons=scan_result.get("vector_reasons", {}),
                        )
                    inv_span.set_attribute("primary_vector", investigation_result.primary_vector)
                    inv_span.set_attribute("primary_cause", investigation_result.primary_cause)
                    inv_span.set_attribute("evidence_count", len(investigation_result.supporting_evidence))
                    inv_span.set_attribute("alert_created", investigation_result.alert_created)
                    inv_span.set_attribute("alert_name", investigation_result.alert_name or "")

                    summary["investigation"] = {
                        "primary_vector": investigation_result.primary_vector,
                        "primary_cause": investigation_result.primary_cause,
                        "evidence_count": len(investigation_result.supporting_evidence),
                        "alert_created": investigation_result.alert_created,
                        "alert_name": investigation_result.alert_name,
                    }
                    logger.info(
                        "Copilot cycle: investigation complete for %s (alert_created=%s)",
                        container_name,
                        investigation_result.alert_created,
                    )
                except Exception as exc:
                    logger.exception(
                        "Copilot cycle: investigation failed for %s: %s", container_name, exc
                    )
                    summary["investigation_error"] = str(exc)

        # ── Step 3: Remediate (CRITICAL only) ─────────────────────────────
        # SAFETY: Remediator has its own internal gate, but we also gate here
        # for defence-in-depth — we never even call remediate() unless CRITICAL.
        if risk_tier == _KILL_TIER:
            summary["steps_executed"].append("remediate")
            reason = (
                investigation_result.primary_cause
                if investigation_result is not None
                else f"trust_score={trust_score:.1f} [{risk_tier}] — no investigation detail available"
            )
            with trace_copilot_step(
                "remediate",
                attributes={
                    "container_id": container_id,
                    "container_name": container_name,
                    "risk_tier": risk_tier,
                    "trust_score": trust_score,
                },
            ) as rem_span:
                try:
                    remediator = Remediator()
                    remediation = await remediator.remediate(
                        container_id=container_id,
                        container_name=container_name,
                        risk_tier=risk_tier,
                        trust_score=trust_score,
                        reason=reason,
                    )
                    rem_span.set_attribute("action_taken", remediation.action_taken)
                    rem_span.set_attribute("remediation_reason", remediation.reason)

                    summary["remediation"] = {
                        "action_taken": remediation.action_taken,
                        "reason": remediation.reason,
                        "timestamp": remediation.timestamp,
                    }
                    summary["final_action"] = "killed" if remediation.action_taken else "kill_attempted_failed"
                    logger.info(
                        "Copilot cycle: remediation for %s — action_taken=%s",
                        container_name,
                        remediation.action_taken,
                    )
                except Exception as exc:
                    logger.exception(
                        "Copilot cycle: remediation failed for %s: %s", container_name, exc
                    )
                    summary["remediation_error"] = str(exc)
        elif risk_tier in _INVESTIGATE_TIERS:
            # HIGH RISK — investigated but not killed
            summary["final_action"] = "investigated_no_kill"
        else:
            # ELEVATED / HEALTHY — no action
            summary["final_action"] = "no_action_required"

        # Record final action on the parent span
        _parent_span.set_attribute("final_action", summary["final_action"])
        _parent_span.set_attribute("steps_executed", str(summary["steps_executed"]))

    logger.info(
        "Copilot cycle complete: %s → final_action=%s",
        container_name,
        summary["final_action"],
    )
    return summary
