"""
Sentinel Copilot Backend — Alert Manager.

Wraps SigNoz's ``signoz_create_alert`` MCP tool to create threshold-based
alert rules for containers whose trust score falls below a critical threshold.

Protocol requirements (read from live MCP resource ``signoz://alert/instructions``):
  - Alert payload shape: version=v5, schemaVersion=v2alpha1, ruleType=threshold_rule
  - compositeQuery: queryType=builder, panelType=graph
  - Threshold op for "below": ``"below"`` with ``matchType="at_least_once"``
  - Channel names must be resolved via ``signoz_list_notification_channels``
    before calling ``signoz_create_alert`` — NEVER hardcode or guess names.
  - If no channel exists, create a webhook channel first.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.observability.mcp_client import MCPClientError, SentinelMCPClient

logger = logging.getLogger(__name__)

# Placeholder webhook URL for demo environments where no real channel exists.
_DEMO_WEBHOOK_URL = "http://localhost:8001/api/v1/webhook/alert-test"
_DEMO_CHANNEL_NAME = "sentinel-webhook-demo"


class AlertManager:
    """Creates and manages SigNoz alert rules for Sentinel Copilot.

    Must be used as an async context manager so the underlying
    ``SentinelMCPClient`` is properly opened and closed::

        async with AlertManager() as am:
            channel = await am.ensure_notification_channel()
            result  = await am.create_trust_score_alert("nginx", threshold=40.0)
    """

    def __init__(self) -> None:
        self._mcp: SentinelMCPClient | None = None

    async def __aenter__(self) -> AlertManager:
        self._mcp = SentinelMCPClient()
        await self._mcp.__aenter__()
        await self._mcp.initialize()
        await self._mcp.send_initialized_notification()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._mcp is not None:
            await self._mcp.__aexit__(*args)
            self._mcp = None

    # ── Internal helpers ─────────────────────────────────────────────────

    def _require_mcp(self) -> SentinelMCPClient:
        if self._mcp is None:
            raise RuntimeError("AlertManager must be used as 'async with AlertManager() as am:'")
        return self._mcp

    def _extract_channel_names(self, raw_result: dict[str, Any]) -> list[str]:
        """Parse channel names from ``signoz_list_notification_channels`` result."""
        # Prefer structuredContent, fall back to parsing text payload
        structured = raw_result.get("structuredContent", {})
        data = structured.get("data") if structured else None

        if data is None:
            # Parse from content[0].text (JSON string)
            content = raw_result.get("content", [])
            if content:
                try:
                    data = json.loads(content[0].get("text", "{}")).get("data", [])
                except (ValueError, KeyError):
                    data = []

        return [ch.get("name", "") for ch in (data or []) if ch.get("name")]

    # ── Public API ───────────────────────────────────────────────────────

    async def ensure_notification_channel(self) -> str:
        """Return a valid SigNoz notification channel name.

        Checks existing channels first.  If none exist, creates a webhook
        channel pointing at a harmless local placeholder URL so that
        ``signoz_create_alert`` has a valid channel to reference.

        Returns:
            The channel name (not ID) to be passed to ``thresholds.spec[].channels``.
        """
        mcp = self._require_mcp()

        # Step 1 — list existing channels
        raw = await mcp.call_tool("signoz_list_notification_channels", {})
        existing = self._extract_channel_names(raw)
        logger.info("MCP signoz_list_notification_channels → %d channel(s): %s", len(existing), existing)

        if existing:
            logger.info("Reusing existing notification channel: %s", existing[0])
            return existing[0]

        # Step 2 — no channels exist → create a webhook placeholder for demo
        logger.info(
            "No notification channels found. Creating demo webhook channel '%s' → %s",
            _DEMO_CHANNEL_NAME,
            _DEMO_WEBHOOK_URL,
        )
        create_result = await mcp.call_tool(
            "signoz_create_notification_channel",
            {
                "type": "webhook",
                "name": _DEMO_CHANNEL_NAME,
                "webhook_url": _DEMO_WEBHOOK_URL,
            },
        )
        logger.info("signoz_create_notification_channel result: %s", create_result)

        # Verify it was created
        raw2 = await mcp.call_tool("signoz_list_notification_channels", {})
        channels_after = self._extract_channel_names(raw2)
        logger.info("Channels after creation: %s", channels_after)

        # Return the new channel name (may differ slightly from what we sent)
        return channels_after[0] if channels_after else _DEMO_CHANNEL_NAME

    async def create_trust_score_alert(
        self,
        container_name: str,
        threshold: float = 40.0,
    ) -> dict[str, Any]:
        """Create a SigNoz threshold alert on ``sentinel.container.trust_score``.

        The alert fires when the trust score for ``container_name`` drops
        below ``threshold`` at least once in the evaluation window.

        Alert payload is composed strictly from the schema documented in
        ``signoz://alert/instructions`` + ``signoz://alert/examples`` MCP
        resources — not guessed.

        Args:
            container_name: Container name as it appears in the metric's
                ``container_name`` label (from the scanner emitter).
            threshold: Score value below which the alert fires (default 40).

        Returns:
            Raw MCP response from ``signoz_create_alert``.
        """
        mcp = self._require_mcp()

        # Get a valid channel name (creates one if needed)
        channel_name = await self.ensure_notification_channel()

        alert_name = f"Sentinel: Low Trust Score — {container_name}"
        description = (
            f"Container '{container_name}' trust score has fallen below "
            f"{threshold}. Sentinel Copilot classifies this as CRITICAL risk."
        )

        # Alert payload composed per signoz://alert/instructions:
        # - version=v5, schemaVersion=v2alpha1, ruleType=threshold_rule
        # - compositeQuery.queryType=builder, panelType=graph
        # - Metric signal: timeAggregation=latest (gauge), spaceAggregation=avg
        # - op="below" fires when score < threshold
        # - filter by container_name attribute (set by SentinelMetricsEmitter)
        payload: dict[str, Any] = {
            "alert": alert_name,
            "alertType": "METRIC_BASED_ALERT",
            "description": description,
            "ruleType": "threshold_rule",
            "version": "v5",
            "schemaVersion": "v2alpha1",
            "condition": {
                "compositeQuery": {
                    "queryType": "builder",
                    "panelType": "graph",
                    "unit": "short",
                    "queries": [
                        {
                            "type": "builder_query",
                            "spec": {
                                "name": "A",
                                "signal": "metrics",
                                "stepInterval": 60,
                                "aggregations": [
                                    {
                                        "metricName": "sentinel.container.trust_score",
                                        "timeAggregation": "latest",
                                        "spaceAggregation": "avg",
                                    }
                                ],
                                "filter": {
                                    "expression": f"container_name = '{container_name}'",
                                },
                                "groupBy": [
                                    {
                                        "name": "container_name",
                                        "fieldContext": "attribute",
                                        "fieldDataType": "string",
                                    }
                                ],
                                "limit": 100,
                                "order": [
                                    {"key": {"name": "__result"}, "direction": "desc"}
                                ],
                                "legend": "{{container_name}} trust score",
                            },
                        }
                    ],
                },
                "selectedQueryName": "A",
                "thresholds": {
                    "kind": "basic",
                    "spec": [
                        {
                            "name": "critical",
                            "target": threshold,
                            "op": "below",
                            "matchType": "at_least_once",
                            "channels": [channel_name],
                        }
                    ],
                },
            },
            "evaluation": {
                "kind": "rolling",
                "spec": {"evalWindow": "5m", "frequency": "1m"},
            },
            "notificationSettings": {
                "groupBy": ["container_name"],
                "renotify": {
                    "enabled": True,
                    "interval": "1h",
                    "alertStates": ["firing"],
                },
            },
            "labels": {"severity": "critical", "managed_by": "sentinel-copilot"},
            "annotations": {
                "summary": f"Trust score for {container_name} is below {threshold}",
                "description": (
                    "Container {{$container_name}} trust score is {{$value}} "
                    f"(threshold: {threshold}). Investigate immediately."
                ),
            },
        }

        logger.info(
            "Creating SigNoz alert '%s' (threshold=%.1f, channel='%s')",
            alert_name,
            threshold,
            channel_name,
        )

        try:
            result = await mcp.call_tool("signoz_create_alert", payload)
            logger.info("signoz_create_alert result: %s", str(result)[:500])
            return {
                "success": True,
                "alert_name": alert_name,
                "channel": channel_name,
                "threshold": threshold,
                "raw_result": result,
            }
        except MCPClientError as exc:
            logger.error("Failed to create alert for '%s': %s", container_name, exc)
            return {
                "success": False,
                "alert_name": alert_name,
                "error": str(exc),
            }
