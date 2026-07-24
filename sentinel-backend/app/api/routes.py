"""
Sentinel Copilot Backend — FastAPI API Routes.

Provides the REST API consumed by the frontend and external callers.
All routes are mounted under ``/api/v1`` via the router prefix.

Data source: the background scanner's in-memory store, updated every
scan cycle.  No direct Docker calls are made from the request path
except for the ``kill`` endpoint.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.core.docker_bridge import kill_container
from app.copilot.investigator import Investigator
from app.models.schemas import InvestigationResult
from app.scanner.background_scanner import get_container_result, get_scan_results

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Container endpoints (new clean API)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/containers", tags=["containers"])
async def list_containers() -> list[dict[str, Any]]:
    """Return all currently-scanned containers with trust scores.

    Each entry includes: ``container_id``, ``container_name``,
    ``trust_score``, ``risk_tier``, ``vector_scores``.
    """
    results = get_scan_results()
    return list(results.values())


@router.get("/containers/{container_id}", tags=["containers"])
async def get_container_detail(container_id: str) -> dict[str, Any]:
    """Detail view for one container: full vector breakdown + reasoning."""
    result = get_container_result(container_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Container '{container_id}' not found in scan results",
        )
    return result


@router.post("/containers/{container_id}/kill", tags=["containers"])
async def kill_container_endpoint(container_id: str) -> dict[str, Any]:
    """Manually stop/kill a container (human-triggered via API/frontend).

    Calls ``docker_bridge.kill_container()`` and returns success/failure.
    This is a MANUAL kill switch — no autonomous logic.
    """
    try:
        success = kill_container(container_id)
        if success:
            return {
                "success": True,
                "message": f"Container '{container_id}' stopped successfully",
            }
        else:
            return {
                "success": False,
                "message": f"Failed to stop container '{container_id}' — it may already be stopped or removed",
            }
    except ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Docker daemon unreachable: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error killing container: {exc}",
        ) from exc


@router.get("/containers/{container_id}/investigation", tags=["containers"], response_model=InvestigationResult)
async def investigate_container(container_id: str) -> InvestigationResult:
    """Run an Investigator pass on one container and return a structured result.

    Reads the container's latest trust-score data from the in-memory scan
    store, enriches it with real SigNoz traces + logs via the MCP client,
    and (for CRITICAL containers) auto-creates a SigNoz alert rule.
    """
    scan_result = get_container_result(container_id)
    if scan_result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Container '{container_id}' not found in scan results. "
                   "Ensure the background scanner has completed at least one cycle.",
        )

    try:
        async with Investigator() as inv:
            return await inv.investigate(
                container_id=scan_result["container_id"],
                container_name=scan_result["container_name"],
                trust_score=scan_result["trust_score"],
                vector_scores=scan_result["vector_scores"],
                vector_reasons=scan_result.get("vector_reasons", {}),
            )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Investigation failed: {exc}",
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Frontend-compatible endpoints
#
# These match the exact paths the frontend's serviceApi.ts currently calls.
# They read from the same scanner in-memory store and reshape the data to
# match the frontend's expected response schemas.
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/metrics/summary", tags=["metrics"])
async def metrics_summary() -> dict[str, Any]:
    """Executive summary metrics — consumed by the frontend's ExecutiveDashboard."""
    results = get_scan_results()
    containers = list(results.values())

    total = len(containers)
    scores = [c["trust_score"] for c in containers]
    avg_score = sum(scores) / total if total else 0.0

    critical_count = sum(1 for c in containers if c["risk_tier"] == "CRITICAL")
    high_count = sum(1 for c in containers if c["risk_tier"] == "HIGH RISK")

    # Determine overall threat level
    if critical_count > 0:
        threat_level = "CRITICAL"
    elif high_count > 0:
        threat_level = "HIGH"
    elif any(c["risk_tier"] == "ELEVATED" for c in containers):
        threat_level = "ELEVATED"
    else:
        threat_level = "LOW"

    # Estimated money saved: $300/container/month baseline, reduction proportional
    # to trust-driven governance actions
    money_saved = int(critical_count * 300 + high_count * 150)

    return {
        "total_containers": total,
        "average_trust_score": round(avg_score, 1),
        "critical_risks": critical_count,
        "high_risks": high_count,
        "threat_level": threat_level,
        "money_saved": money_saved,
    }


@router.get("/discovery/shadow-ai", tags=["discovery"])
async def discovery_shadow_ai() -> list[dict[str, Any]]:
    """Container discovery — consumed by the frontend's DiscoveryDashboard.

    Returns containers shaped with ``trust_score``, ``is_sanctioned``,
    ``image``, etc. to match what ``serviceApi.ts`` ``getDiscovery()`` expects.
    """
    results = get_scan_results()
    out: list[dict[str, Any]] = []

    for cid, res in results.items():
        identity_score = res.get("vector_scores", {}).get("identity", 0)
        out.append({
            "id": cid,
            "name": res["container_name"],
            "status": "running",
            "trust_score": round(res["trust_score"], 1),
            "risk_tier": res["risk_tier"],
            "is_sanctioned": identity_score >= 80,
            "image": res["container_name"],
            "trust_details": res.get("vector_scores", {}),
            "type": "mcp_server",
        })

    return out


@router.get("/security/alerts", tags=["security"])
async def security_alerts() -> list[dict[str, Any]]:
    """Security alerts derived from scan results.

    Any container in CRITICAL or HIGH RISK tier generates an alert.
    """
    results = get_scan_results()
    alerts: list[dict[str, Any]] = []

    for cid, res in results.items():
        tier = res["risk_tier"]
        if tier in ("CRITICAL", "HIGH RISK"):
            severity = "critical" if tier == "CRITICAL" else "high"
            reasons = res.get("vector_reasons", {})
            # Build description from worst vector reasons
            desc_parts = [
                f"{k}: {v}" for k, v in reasons.items()
                if any(neg in v.lower() for neg in ("root", "privileged", "not in", "no ", "exposed", "critical port"))
            ]
            alerts.append({
                "id": f"alert-{cid[:8]}-{uuid.uuid4().hex[:6]}",
                "severity": severity,
                "agentId": cid,
                "agentName": res["container_name"],
                "violationType": f"{tier} — Trust Score {res['trust_score']:.0f}",
                "description": "; ".join(desc_parts) if desc_parts else f"Container scored {res['trust_score']:.0f} ({tier})",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "active",
                "recommended_action": "kill" if tier == "CRITICAL" else "investigate",
            })

    return alerts


@router.get("/governance/terminate/{container_id}", tags=["governance"])
@router.post("/governance/terminate/{container_id}", tags=["governance"])
async def governance_terminate(container_id: str) -> dict[str, Any]:
    """Frontend-compatible terminate endpoint (wraps the kill endpoint)."""
    return await kill_container_endpoint(container_id)


@router.get("/governance/audit-logs", tags=["governance"])
async def governance_audit_logs(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent governance audit log entries.

    Currently generated from the last scan cycle results rather than a
    persistent audit log (that will come with the full audit subsystem).
    """
    results = get_scan_results()
    logs: list[dict[str, Any]] = []

    for cid, res in results.items():
        logs.append({
            "id": f"log-{cid[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_name": res["container_name"],
            "action": f"trust_scan → {res['risk_tier']} ({res['trust_score']:.0f})",
            "status": "success",
            "details": f"Vectors: id={res['vector_scores'].get('identity', 0):.0f} "
                       f"cfg={res['vector_scores'].get('configuration', 0):.0f} "
                       f"net={res['vector_scores'].get('network', 0):.0f} "
                       f"res={res['vector_scores'].get('resources', 0):.0f}",
            "tool": "background_scanner",
            "duration": 50,
        })

    return logs[:limit]


@router.get("/metrics/cost", tags=["metrics"])
async def metrics_cost() -> dict[str, Any]:
    """Cost analytics — consumed by the frontend's CostDashboard.

    Derives cost data from container scan results. Each container is
    estimated at ~$300/month baseline.
    """
    results = get_scan_results()
    containers = list(results.values())
    total = len(containers)

    total_spend = total * 300
    critical = sum(1 for c in containers if c["risk_tier"] == "CRITICAL")
    total_saved = critical * 300
    savings_pct = round((total_saved / max(total_spend, 1)) * 100, 1)

    return {
        "totalSpend": total_spend,
        "totalSaved": total_saved,
        "savingsPercent": savings_pct,
        "burnRate": round(total_spend / 30, 2) if total else 0,
        "projectedMonthly": total_spend,
        "agentCosts": [
            {
                "agentName": c["container_name"],
                "cost": 10,
                "trend": -5 if c["risk_tier"] == "HEALTHY" else 12,
                "trustScore": round(c["trust_score"], 1),
            }
            for c in containers[:5]
        ],
        "dailyBurn": [
            {"date": f"Day {i+1}", "cost": max(50, total_spend // 30 - i * 2), "optimized": max(30, total_spend // 30 - i * 5)}
            for i in range(7)
        ],
        "optimizationInsights": [
            {"title": "Kill CRITICAL containers", "impact": f"Remove {critical} high-risk containers", "savings": critical * 300},
            {"title": "Enforce resource limits", "impact": "Set memory/CPU limits on all containers", "savings": 150},
        ],
    }


@router.get("/system/health", tags=["system"])
async def system_health() -> dict[str, Any]:
    """System health overview — consumed by the frontend."""
    results = get_scan_results()
    containers = list(results.values())
    total = len(containers)
    scores = [c["trust_score"] for c in containers]

    critical = sum(1 for c in containers if c["risk_tier"] == "CRITICAL")
    healthy = sum(1 for c in containers if c["risk_tier"] == "HEALTHY")

    return {
        "average_trust_score": round(sum(scores) / total, 1) if total else 0,
        "total_containers": total,
        "critical_containers": critical,
        "healthy_containers": healthy,
        "status": "operational" if total > 0 else "no_containers",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
