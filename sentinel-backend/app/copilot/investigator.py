"""
Sentinel Copilot Backend — Copilot Investigator.

Given a container's trust score + vector breakdown from the scanner, the
Investigator enriches the finding with real telemetry from SigNoz (traces,
logs) via the MCP client.  If the container is in CRITICAL risk tier it also
auto-creates a SigNoz alert rule ("Incident → Insight → Alert" loop).

Telemetry correlation is best-effort: if the container_name does not match
an instrumented SigNoz service, the call returns gracefully with an empty
evidence list rather than raising.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.models.schemas import InvestigationResult, TelemetryEvidence
from app.observability.alert_manager import AlertManager
from app.observability.mcp_client import MCPClientError, SentinelMCPClient

logger = logging.getLogger(__name__)


class Investigator:
    """Enriches a scanner result with real SigNoz telemetry and generates alerts.

    Usage::

        async with Investigator() as inv:
            result = await inv.investigate(
                container_id="abc123",
                container_name="nginx",
                trust_score=28.0,
                vector_scores={"identity": 20, "configuration": 35, "network": 50, "resources": 80},
                vector_reasons={"identity": "...", "configuration": "...", ...},
            )
    """

    def __init__(self) -> None:
        self._mcp: SentinelMCPClient | None = None

    async def __aenter__(self) -> Investigator:
        self._mcp = SentinelMCPClient()
        await self._mcp.__aenter__()
        await self._mcp.initialize()
        await self._mcp.send_initialized_notification()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._mcp is not None:
            await self._mcp.__aexit__(*args)
            self._mcp = None

    # ── Helpers ──────────────────────────────────────────────────────────

    def _require_mcp(self) -> SentinelMCPClient:
        if self._mcp is None:
            raise RuntimeError("Investigator must be used as 'async with Investigator() as inv:'")
        return self._mcp

    def _find_primary_vector(
        self,
        vector_scores: dict[str, float],
    ) -> tuple[str, float]:
        """Return (vector_name, score) for the lowest-scoring vector."""
        return min(vector_scores.items(), key=lambda kv: kv[1])

    def _extract_telemetry_snippets(
        self,
        raw_result: dict[str, Any],
        source: str,
    ) -> list[TelemetryEvidence]:
        """Extract human-readable snippets from an MCP search_traces / search_logs result."""
        evidence: list[TelemetryEvidence] = []

        content = raw_result.get("content", [])
        if not content:
            return evidence

        # The first content item is always a JSON string with the full data
        text = content[0].get("text", "") if content else ""
        try:
            data = json.loads(text)
        except (ValueError, KeyError):
            return evidence

        status = data.get("status", "")
        if status != "success":
            return evidence

        results = (
            data.get("data", {})
            .get("data", {})
            .get("results", [])
        )

        for result_set in results:
            rows = result_set.get("rows") or []
            for row in rows[:3]:  # At most 3 snippets per source
                snippet_parts: list[str] = []
                if source == "traces":
                    svc = row.get("serviceName", "")
                    op = row.get("name", "")
                    dur_ns = row.get("durationNano", 0)
                    dur_ms = dur_ns / 1_000_000 if dur_ns else 0
                    has_err = row.get("hasError", False)
                    snippet_parts.append(f"[{source}] service={svc} op={op} duration={dur_ms:.0f}ms error={has_err}")
                elif source == "logs":
                    sev = row.get("severity_text") or row.get("severityText", "")
                    body = row.get("body", "")[:120]
                    svc = row.get("serviceName", "")
                    snippet_parts.append(f"[{source}] svc={svc} severity={sev} body={body!r}")
                else:
                    snippet_parts.append(f"[{source}] {str(row)[:200]}")

                if snippet_parts:
                    evidence.append(
                        TelemetryEvidence(
                            source=source,
                            snippet=snippet_parts[0],
                            raw=row,
                        )
                    )

        return evidence

    # ── Core investigate method ──────────────────────────────────────────

    async def investigate(
        self,
        container_id: str,
        container_name: str,
        trust_score: float,
        vector_scores: dict[str, float],
        vector_reasons: dict[str, str],
    ) -> InvestigationResult:
        """Investigate a container and return a structured ``InvestigationResult``.

        Steps:
        1. Identify the primary (lowest-scoring) vector.
        2. Attempt to correlate with SigNoz traces + logs via MCP client.
        3. Build a human-readable summary.
        4. If risk is CRITICAL, auto-create a SigNoz alert rule.

        Args:
            container_id: Docker container ID from the scanner.
            container_name: Docker container name (may not be a SigNoz service).
            trust_score: Weighted composite trust score (0–100).
            vector_scores: Per-vector scores dict.
            vector_reasons: Per-vector reason strings from the scorer.

        Returns:
            ``InvestigationResult`` Pydantic model.
        """
        mcp = self._require_mcp()

        # Determine risk tier from trust score (mirrors scorer logic)
        if trust_score < 40:
            risk_tier = "CRITICAL"
        elif trust_score < 60:
            risk_tier = "HIGH RISK"
        elif trust_score < 80:
            risk_tier = "ELEVATED"
        else:
            risk_tier = "HEALTHY"

        # Step 1: Find the lowest-scoring vector
        primary_vector, primary_score = self._find_primary_vector(vector_scores)
        primary_reason = vector_reasons.get(
            primary_vector,
            f"Vector '{primary_vector}' scored {primary_score:.0f}/100",
        )
        primary_cause = f"{primary_vector} ({primary_score:.0f}/100): {primary_reason}"

        logger.info(
            "Investigating container %s (%s): trust=%.1f [%s], primary_vector=%s (%.1f)",
            container_name,
            container_id[:12],
            trust_score,
            risk_tier,
            primary_vector,
            primary_score,
        )

        # Step 2: Correlate with real telemetry from SigNoz
        supporting_evidence: list[TelemetryEvidence] = []

        # --- Logs ---
        try:
            log_result = await mcp.search_logs(
                service_name=container_name,
                limit=5,
                time_range="1h",
            )
            log_evidence = self._extract_telemetry_snippets(log_result, "logs")
            supporting_evidence.extend(log_evidence)
            logger.info(
                "Log correlation for '%s': %d snippet(s) found",
                container_name,
                len(log_evidence),
            )
        except MCPClientError as exc:
            logger.warning("Log search for '%s' failed: %s", container_name, exc)

        # --- Traces ---
        try:
            trace_result = await mcp.search_traces(
                service_name=container_name,
                limit=5,
                time_range="1h",
            )
            trace_evidence = self._extract_telemetry_snippets(trace_result, "traces")
            supporting_evidence.extend(trace_evidence)
            logger.info(
                "Trace correlation for '%s': %d snippet(s) found",
                container_name,
                len(trace_evidence),
            )
        except MCPClientError as exc:
            logger.warning("Trace search for '%s' failed: %s", container_name, exc)

        # Step 3: Build human-readable summary
        no_telemetry_msg = (
            " No additional telemetry correlation was found in SigNoz traces or"
            " logs — the container may not be instrumented with OpenTelemetry."
            if not supporting_evidence
            else f" {len(supporting_evidence)} telemetry signal(s) were found that may corroborate this finding."
        )

        vector_summary = ", ".join(
            f"{v}={s:.0f}" for v, s in sorted(vector_scores.items(), key=lambda kv: kv[1])
        )

        summary = (
            f"Container '{container_name}' (ID: {container_id[:12]}) has been classified as"
            f" {risk_tier} with a trust score of {trust_score:.1f}/100."
            f" The primary concern is the {primary_vector} vector (score: {primary_score:.0f}/100):"
            f" {primary_reason}."
            f" Full vector breakdown: [{vector_summary}]."
            f"{no_telemetry_msg}"
        )

        # Step 4: Auto-create a SigNoz alert if this container is CRITICAL
        alert_created = False
        alert_name: str | None = None

        if risk_tier == "CRITICAL":
            logger.info(
                "Container '%s' is CRITICAL — triggering automatic alert creation",
                container_name,
            )
            try:
                async with AlertManager() as am:
                    alert_result = await am.create_trust_score_alert(
                        container_name=container_name,
                        threshold=40.0,
                    )
                    alert_created = alert_result.get("success", False)
                    alert_name = alert_result.get("alert_name")
                    logger.info(
                        "Alert creation for '%s': success=%s name=%s",
                        container_name,
                        alert_created,
                        alert_name,
                    )
            except Exception as exc:
                logger.error(
                    "Alert creation failed for '%s': %s — investigation continues",
                    container_name,
                    exc,
                )

        return InvestigationResult(
            container_id=container_id,
            container_name=container_name,
            trust_score=trust_score,
            risk_tier=risk_tier,
            primary_cause=primary_cause,
            primary_vector=primary_vector,
            supporting_evidence=supporting_evidence,
            summary=summary,
            alert_created=alert_created,
            alert_name=alert_name,
        )
