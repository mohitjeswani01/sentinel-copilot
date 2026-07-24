"""
Sentinel Copilot — API Routes & MCP Client Tests.

Tests for Part A (FastAPI routes) and Part B (MCP client) of the
API layer + MCP foundation task.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.observability.mcp_client import SentinelMCPClient, MCPClientError, MCPToolCallError


# ═══════════════════════════════════════════════════════════════════════════
# PART A — API ROUTES
# ═══════════════════════════════════════════════════════════════════════════

client = TestClient(app, raise_server_exceptions=False)


class TestHealthEndpoints:
    """Test system health endpoints."""

    def test_healthz_returns_ok(self) -> None:
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "Sentinel" in data["service"]


class TestContainerRoutes:
    """Test /api/v1/containers endpoints."""

    def test_list_containers_returns_list(self) -> None:
        """GET /containers should return a list (may be empty without Docker)."""
        response = client.get("/api/v1/containers")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_nonexistent_container_returns_404(self) -> None:
        """GET /containers/{id} for unknown container → 404."""
        response = client.get("/api/v1/containers/nonexistent-id-12345")
        assert response.status_code == 404

    @patch("app.scanner.background_scanner._last_scan_results", {
        "abc123": {
            "container_id": "abc123",
            "container_name": "test-container",
            "trust_score": 72.5,
            "risk_tier": "ELEVATED",
            "vector_scores": {"identity": 100, "configuration": 75, "network": 50, "resources": 65},
            "vector_reasons": {
                "identity": "Image 'nginx' matches sanctioned whitelist",
                "configuration": "Running as root",
                "network": "Port 80 exposed on 0.0.0.0",
                "resources": "No memory limit",
            },
        }
    })
    def test_list_containers_with_mock_data(self) -> None:
        """GET /containers returns data when scanner has results."""
        response = client.get("/api/v1/containers")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["container_id"] == "abc123"
        assert data[0]["trust_score"] == 72.5
        assert data[0]["risk_tier"] == "ELEVATED"

    @patch("app.scanner.background_scanner._last_scan_results", {
        "abc123": {
            "container_id": "abc123",
            "container_name": "test-container",
            "trust_score": 72.5,
            "risk_tier": "ELEVATED",
            "vector_scores": {"identity": 100, "configuration": 75, "network": 50, "resources": 65},
            "vector_reasons": {"identity": "ok", "configuration": "ok", "network": "ok", "resources": "ok"},
        }
    })
    def test_get_container_detail_with_mock_data(self) -> None:
        """GET /containers/{id} returns full detail for known container."""
        response = client.get("/api/v1/containers/abc123")
        assert response.status_code == 200
        data = response.json()
        assert data["container_name"] == "test-container"
        assert "vector_reasons" in data


class TestFrontendCompatRoutes:
    """Test frontend-compatible endpoints."""

    def test_metrics_summary_returns_dict(self) -> None:
        response = client.get("/api/v1/metrics/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_containers" in data
        assert "average_trust_score" in data
        assert "threat_level" in data

    def test_discovery_shadow_ai_returns_list(self) -> None:
        response = client.get("/api/v1/discovery/shadow-ai")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_security_alerts_returns_list(self) -> None:
        response = client.get("/api/v1/security/alerts")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_audit_logs_returns_list(self) -> None:
        response = client.get("/api/v1/governance/audit-logs")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_metrics_cost_returns_dict(self) -> None:
        response = client.get("/api/v1/metrics/cost")
        assert response.status_code == 200
        data = response.json()
        assert "totalSpend" in data
        assert "totalSaved" in data


# ═══════════════════════════════════════════════════════════════════════════
# PART B — MCP CLIENT
# ═══════════════════════════════════════════════════════════════════════════

class TestMCPClient:
    """Unit tests for the SentinelMCPClient (mocked — no real server needed)."""

    @pytest.mark.anyio
    async def test_initialize_sends_correct_payload(self) -> None:
        """initialize() should send a JSON-RPC request with method='initialize'."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "signoz-mcp", "version": "0.1.0"},
            },
        }
        mock_response.raise_for_status = MagicMock()

        async with SentinelMCPClient(mcp_url="http://fake:8000/mcp") as mcp:
            mcp._client = AsyncMock()
            mcp._client.post = AsyncMock(return_value=mock_response)

            result = await mcp.initialize()
            assert "protocolVersion" in result or "capabilities" in result

    @pytest.mark.anyio
    async def test_unreachable_server_raises_mcp_error(self) -> None:
        """Connection failure should raise MCPClientError."""
        async with SentinelMCPClient(mcp_url="http://nonexistent:9999/mcp", timeout=1.0) as mcp:
            with pytest.raises(MCPClientError):
                await mcp.initialize()

    @pytest.mark.anyio
    async def test_jsonrpc_error_raises_tool_call_error(self) -> None:
        """A JSON-RPC error response should raise MCPToolCallError."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        }
        mock_response.raise_for_status = MagicMock()

        async with SentinelMCPClient(mcp_url="http://fake:8000/mcp") as mcp:
            mcp._client = AsyncMock()
            mcp._client.post = AsyncMock(return_value=mock_response)

            with pytest.raises(MCPToolCallError, match="Method not found"):
                await mcp.list_available_tools()

    def test_empty_api_key_raises_error(self) -> None:
        """Creating client with empty api_key should raise MCPClientError."""
        with pytest.raises(MCPClientError, match="SIGNOZ_API_KEY is empty"):
            SentinelMCPClient(mcp_url="http://fake:8000/mcp", api_key="")

    @pytest.mark.anyio
    async def test_convenience_wrappers_call_correct_tools(self) -> None:
        """Convenience wrappers should invoke correct tool names and parameters."""
        async with SentinelMCPClient(mcp_url="http://fake:8000/mcp") as mcp:
            mcp.call_tool = AsyncMock(return_value={"status": "success"})

            await mcp.query_services()
            mcp.call_tool.assert_called_with("signoz_list_services", {"timeRange": "6h", "limit": 50})

            await mcp.search_traces(service_name="payment-service", limit=5)
            mcp.call_tool.assert_called_with("signoz_search_traces", {"limit": 5, "timeRange": "1h", "service": "payment-service"})

            await mcp.search_logs(service_name="payment-service", search_text="error")
            mcp.call_tool.assert_called_with("signoz_search_logs", {"limit": 10, "timeRange": "1h", "service": "payment-service", "searchText": "error"})

            await mcp.get_metrics(metric_name="container_cpu_usage")
            mcp.call_tool.assert_called_with("signoz_query_metrics", {"metricName": "container_cpu_usage", "timeRange": "1h"})
