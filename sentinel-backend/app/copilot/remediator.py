"""
Sentinel Copilot Backend — Autonomous Remediator.

SAFETY POLICY (non-negotiable):
  Only containers in the CRITICAL risk tier (trust_score < 40) may ever be
  autonomously killed.  HIGH RISK, ELEVATED, and HEALTHY containers are
  NEVER touched — the call returns immediately with action_taken=False and
  the skip is logged and audited.

This is enforced by an explicit tier-check at the START of ``remediate()``
before any docker call is attempted.  The copilot loop also gate-checks
before calling this method, providing defence-in-depth.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.docker_bridge import kill_container
from app.models.schemas import (
    AuditLogEntry,
    RemediationResult,
    append_audit_entry,
)

logger = logging.getLogger(__name__)

# The ONLY tier that may trigger an autonomous kill.
_KILL_TIER = "CRITICAL"


class Remediator:
    """Autonomous container remediator.

    Usage::

        remediator = Remediator()
        result = await remediator.remediate(
            container_id="abc123",
            container_name="shadow-llm",
            risk_tier="CRITICAL",
            trust_score=22.0,
            reason="identity (20/100): Unsanctioned image; configuration (30/100): Running as root",
        )
    """

    async def remediate(
        self,
        container_id: str,
        container_name: str,
        risk_tier: str,
        trust_score: float,
        reason: str,
    ) -> RemediationResult:
        """Evaluate whether to autonomously kill ``container_id``.

        The container is killed ONLY if ``risk_tier == "CRITICAL"``.
        Every call — kill or skip — is written to the append-only audit log.

        Args:
            container_id: Docker container ID (full or short).
            container_name: Human-readable container name for log/audit.
            risk_tier: Risk classification from the trust engine scorer.
            trust_score: Numeric trust score 0–100.
            reason: Human-readable justification string (from InvestigationResult).

        Returns:
            ``RemediationResult`` with action_taken and reason.
        """
        # ── SAFETY GATE (layer 1) ──────────────────────────────────────────
        if risk_tier != _KILL_TIER:
            skip_reason = (
                f"Risk tier is '{risk_tier}' (trust={trust_score:.1f}) — "
                f"autonomous kill requires '{_KILL_TIER}'. No action taken."
            )
            logger.info(
                "Remediator SKIPPED container '%s' (%s): %s",
                container_name,
                container_id[:12],
                skip_reason,
            )
            append_audit_entry(AuditLogEntry(
                container_id=container_id,
                container_name=container_name,
                trust_score=trust_score,
                risk_tier=risk_tier,
                action="skipped",
                reason=skip_reason,
            ))
            return RemediationResult(
                container_id=container_id,
                container_name=container_name,
                action_taken=False,
                reason=skip_reason,
            )

        # ── AUTONOMOUS KILL (CRITICAL only) ───────────────────────────────
        logger.warning(
            "Remediator KILLING container '%s' (%s) — trust=%.1f [%s]: %s",
            container_name,
            container_id[:12],
            trust_score,
            risk_tier,
            reason,
        )

        killed = False
        kill_reason = reason

        try:
            # kill_container is synchronous (Docker SDK) — offload to thread pool
            killed = await asyncio.get_event_loop().run_in_executor(
                None,
                kill_container,
                container_id,
            )
            if killed:
                kill_reason = (
                    f"Autonomously killed — trust_score={trust_score:.1f} [{risk_tier}]. "
                    f"Root cause: {reason}"
                )
                logger.warning(
                    "Remediator KILL SUCCESS: container '%s' (%s) stopped",
                    container_name,
                    container_id[:12],
                )
            else:
                kill_reason = (
                    f"Kill returned False (container may already be stopped) — "
                    f"trust_score={trust_score:.1f} [{risk_tier}]. Root cause: {reason}"
                )
                logger.error(
                    "Remediator KILL FAILED (False returned): container '%s' (%s)",
                    container_name,
                    container_id[:12],
                )
        except ConnectionError as exc:
            kill_reason = f"Docker daemon unreachable — could not kill: {exc}"
            logger.error(
                "Remediator KILL FAILED (ConnectionError) for '%s': %s",
                container_name,
                exc,
            )
        except Exception as exc:
            kill_reason = f"Unexpected error during kill: {exc}"
            logger.exception(
                "Remediator KILL FAILED (unexpected) for '%s': %s",
                container_name,
                exc,
            )

        # Write audit entry regardless of kill success/failure
        append_audit_entry(AuditLogEntry(
            container_id=container_id,
            container_name=container_name,
            trust_score=trust_score,
            risk_tier=risk_tier,
            action="autonomous_kill",
            reason=kill_reason,
        ))

        return RemediationResult(
            container_id=container_id,
            container_name=container_name,
            action_taken=killed,
            reason=kill_reason,
        )
