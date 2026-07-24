"""
Sentinel Copilot — Copilot Investigator & Alert Manager Unit Tests.

Tests for Part A (Copilot Investigator) and Part B (Alert Manager) of
Issues #8 & #9. All MCP calls are mocked for unit testing.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.copilot.investigator import Investigator
from app.main import app
from app.models.schemas import InvestigationResult
from app.observability.alert_manager import AlertManager

client = TestClient(app, raise_server_exceptions=False)


class TestInvestigationRoute:
    """Test GET /api/v1/containers/{id}/investigation."""

    def test_investigation_unknown_container_returns_404(self) -> None:
        """Endpoint should 404 for unknown container."""
        response = client.get("/api/v1/containers/unknown-container-999/investigation")
        assert response.status_code == 404

    @patch("app.scanner.background_scanner._last_scan_results", {
        "cont-123": {
            "container_id": "cont-123",
            "container_name": "vulnerable-app",
            "trust_score": 35.0,
            "risk_tier": "CRITICAL",
            "vector_scores": {"identity": 20.0, "configuration": 40.0, "network": 50.0, "resources": 80.0},
            "vector_reasons": {
                "identity": "Unsanctioned image 'vulnerable/app:latest'",
                "configuration": "Running as root",
            },
        }
    })
    @patch.object(Investigator, "__aenter__")
    @patch.object(Investigator, "__aexit__")
    def test_investigation_known_container_returns_result(
        self, mock_exit: AsyncMock, mock_enter: AsyncMock
    ) -> None:
        """Endpoint should trigger investigation and return InvestigationResult schema."""
        mock_inv_instance = MagicMock()
        expected_result = InvestigationResult(
            container_id="cont-123",
            container_name="vulnerable-app",
            trust_score=35.0,
            risk_tier="CRITICAL",
            primary_cause="identity (20/100): Unsanctioned image 'vulnerable/app:latest'",
            primary_vector="identity",
            supporting_evidence=[],
            summary="Container 'vulnerable-app' classified as CRITICAL.",
            alert_created=True,
            alert_name="Sentinel: Low Trust Score — vulnerable-app",
        )
        mock_inv_instance.investigate = AsyncMock(return_value=expected_result)
        mock_enter.return_value = mock_inv_instance

        response = client.get("/api/v1/containers/cont-123/investigation")
        assert response.status_code == 200
        data = response.json()
        assert data["container_id"] == "cont-123"
        assert data["risk_tier"] == "CRITICAL"
        assert data["alert_created"] is True


class TestInvestigator:
    """Unit tests for Investigator logic."""

    @pytest.mark.anyio
    async def test_investigate_elevated_container(self) -> None:
        """Investigating an ELEVATED container identifies lowest vector and does NOT create alert."""
        inv = Investigator()
        inv._mcp = MagicMock()
        inv._mcp.search_logs = AsyncMock(return_value={"content": []})
        inv._mcp.search_traces = AsyncMock(return_value={"content": []})

        result = await inv.investigate(
            container_id="test-id-1",
            container_name="shadow-llm-service",
            trust_score=65.0,
            vector_scores={"identity": 100.0, "configuration": 40.0, "network": 70.0, "resources": 80.0},
            vector_reasons={"configuration": "Running as root user"},
        )

        assert result.risk_tier == "ELEVATED"
        assert result.primary_vector == "configuration"
        assert "configuration" in result.primary_cause
        assert result.alert_created is False
        assert "no additional telemetry correlation was found" in result.summary.lower()


class TestAlertManager:
    """Unit tests for AlertManager logic."""

    @pytest.mark.anyio
    async def test_ensure_notification_channel_reuses_existing(self) -> None:
        """Should return existing channel name if signoz_list_notification_channels has one."""
        am = AlertManager()
        am._mcp = MagicMock()
        am._mcp.call_tool = AsyncMock(return_value={
            "structuredContent": {
                "data": [{"id": "chan-1", "name": "existing-slack"}]
            }
        })

        channel_name = await am.ensure_notification_channel()
        assert channel_name == "existing-slack"

    @pytest.mark.anyio
    async def test_ensure_notification_channel_creates_placeholder_when_empty(self) -> None:
        """Should create a webhook channel if no channels exist."""
        am = AlertManager()
        am._mcp = MagicMock()

        # 1st call: empty list; 2nd call (create): success; 3rd call (list after): returns newly created
        am._mcp.call_tool = AsyncMock(side_effect=[
            {"structuredContent": {"data": []}},
            {"status": "success"},
            {"structuredContent": {"data": [{"name": "sentinel-webhook-demo"}]}},
        ])

        channel_name = await am.ensure_notification_channel()
        assert channel_name == "sentinel-webhook-demo"
