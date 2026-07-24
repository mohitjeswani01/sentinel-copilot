"""
Sentinel Copilot — Remediator, Loop & Audit Log Unit Tests.

All Docker and MCP calls are mocked.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.copilot.loop import run_copilot_cycle
from app.copilot.remediator import Remediator
from app.main import app
from app.models.schemas import (
    AuditLogEntry,
    InvestigationResult,
    RemediationResult,
    _audit_log,
    append_audit_entry,
    get_audit_log,
)

client = TestClient(app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════════════════
# REMEDIATOR UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestRemediator:
    """Safety-critical tests for Remediator."""

    @pytest.mark.anyio
    async def test_skip_healthy_container(self) -> None:
        """HEALTHY container must NEVER be killed."""
        rem = Remediator()
        result = await rem.remediate(
            container_id="healthy-123",
            container_name="nginx-healthy",
            risk_tier="HEALTHY",
            trust_score=95.0,
            reason="trust_score=95 [HEALTHY]",
        )
        assert result.action_taken is False
        assert "HEALTHY" in result.reason

    @pytest.mark.anyio
    async def test_skip_elevated_container(self) -> None:
        """ELEVATED container must NEVER be killed."""
        rem = Remediator()
        result = await rem.remediate(
            container_id="elevated-456",
            container_name="redis-elevated",
            risk_tier="ELEVATED",
            trust_score=65.0,
            reason="trust_score=65 [ELEVATED]",
        )
        assert result.action_taken is False
        assert "ELEVATED" in result.reason

    @pytest.mark.anyio
    async def test_skip_high_risk_container(self) -> None:
        """HIGH RISK container must NEVER be auto-killed (investigate only)."""
        rem = Remediator()
        result = await rem.remediate(
            container_id="highrisk-789",
            container_name="postgres-highrisk",
            risk_tier="HIGH RISK",
            trust_score=52.0,
            reason="trust_score=52 [HIGH RISK]",
        )
        assert result.action_taken is False
        assert "HIGH RISK" in result.reason

    @pytest.mark.anyio
    @patch("app.copilot.remediator.kill_container", return_value=True)
    async def test_kill_critical_container(self, mock_kill: MagicMock) -> None:
        """CRITICAL container should trigger autonomous kill."""
        initial_audit_len = len(_audit_log)
        rem = Remediator()
        result = await rem.remediate(
            container_id="critical-aaa",
            container_name="shadow-llm",
            risk_tier="CRITICAL",
            trust_score=18.0,
            reason="identity (18/100): unsanctioned image",
        )
        assert result.action_taken is True
        assert mock_kill.called
        # Audit entry should have been written
        assert len(_audit_log) == initial_audit_len + 1
        audit = _audit_log[-1]
        assert audit.action == "autonomous_kill"
        assert audit.container_name == "shadow-llm"

    @pytest.mark.anyio
    async def test_skip_writes_audit_entry(self) -> None:
        """A skip (non-CRITICAL) must still be written to the audit log."""
        initial_audit_len = len(_audit_log)
        rem = Remediator()
        await rem.remediate(
            container_id="skip-bbb",
            container_name="some-container",
            risk_tier="ELEVATED",
            trust_score=70.0,
            reason="test skip",
        )
        assert len(_audit_log) == initial_audit_len + 1
        assert _audit_log[-1].action == "skipped"


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT LOG TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditLog:
    """Tests for in-memory audit log store."""

    def test_get_audit_log_returns_newest_first(self) -> None:
        """Audit log should return entries newest-first."""
        initial_len = len(_audit_log)
        e1 = AuditLogEntry(
            container_id="z1", container_name="a", trust_score=10.0,
            risk_tier="CRITICAL", action="autonomous_kill", reason="r1",
        )
        e2 = AuditLogEntry(
            container_id="z2", container_name="b", trust_score=20.0,
            risk_tier="ELEVATED", action="skipped", reason="r2",
        )
        append_audit_entry(e1)
        append_audit_entry(e2)
        log = get_audit_log()
        # e2 was appended last, should be first in reversed output
        assert log[0].container_id == "z2"
        assert log[1].container_id == "z1"


# ═══════════════════════════════════════════════════════════════════════════
# COPILOT LOOP TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestCopilotLoop:
    """Tests for run_copilot_cycle()."""

    @pytest.mark.anyio
    async def test_cycle_unknown_container_returns_error(self) -> None:
        """If container not in scan store, cycle returns error key."""
        result = await run_copilot_cycle("no-such-container-id-9999")
        assert "error" in result

    @pytest.mark.anyio
    @patch("app.scanner.background_scanner._last_scan_results", {
        "healthy-001": {
            "container_id": "healthy-001",
            "container_name": "nginx",
            "trust_score": 92.0,
            "risk_tier": "HEALTHY",
            "vector_scores": {"identity": 100.0, "configuration": 95.0, "network": 90.0, "resources": 85.0},
            "vector_reasons": {},
        }
    })
    async def test_cycle_healthy_container_takes_no_action(self) -> None:
        """Healthy container: no investigation, no kill."""
        result = await run_copilot_cycle("healthy-001")
        assert result["final_action"] == "no_action_required"
        assert "investigate" not in result.get("steps_executed", [])
        assert "remediate" not in result.get("steps_executed", [])

    @pytest.mark.anyio
    @patch("app.scanner.background_scanner._last_scan_results", {
        "critical-001": {
            "container_id": "critical-001",
            "container_name": "shadow-llm",
            "trust_score": 22.0,
            "risk_tier": "CRITICAL",
            "vector_scores": {"identity": 15.0, "configuration": 25.0, "network": 30.0, "resources": 80.0},
            "vector_reasons": {"identity": "Unsanctioned image"},
        }
    })
    @patch.object(__import__("app.copilot.investigator", fromlist=["Investigator"]).Investigator, "__aenter__")
    @patch.object(__import__("app.copilot.investigator", fromlist=["Investigator"]).Investigator, "__aexit__")
    @patch.object(__import__("app.copilot.investigator", fromlist=["Investigator"]).Investigator, "investigate")
    @patch("app.copilot.remediator.kill_container", return_value=True)
    async def test_cycle_critical_container_investigates_and_kills(
        self,
        mock_kill: MagicMock,
        mock_investigate: MagicMock,
        mock_exit: AsyncMock,
        mock_enter: AsyncMock,
    ) -> None:
        """CRITICAL container: investigate + kill both execute."""
        mock_inv_instance = MagicMock()
        mock_inv_instance.investigate = AsyncMock(return_value=InvestigationResult(
            container_id="critical-001",
            container_name="shadow-llm",
            trust_score=22.0,
            risk_tier="CRITICAL",
            primary_cause="identity (15/100): Unsanctioned image",
            primary_vector="identity",
            supporting_evidence=[],
            summary="CRITICAL risk.",
        ))
        mock_enter.return_value = mock_inv_instance

        result = await run_copilot_cycle("critical-001")
        assert "investigate" in result.get("steps_executed", [])
        assert "remediate" in result.get("steps_executed", [])
        assert result["final_action"] == "killed"
        assert mock_kill.called


# ═══════════════════════════════════════════════════════════════════════════
# COPILOT-CYCLE API ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestCopilotCycleRoute:
    """Tests for POST /api/v1/containers/{id}/run-copilot-cycle."""

    def test_cycle_unknown_container_returns_200_with_error(self) -> None:
        """Unknown container returns 200 with error key (cycle always succeeds at HTTP level)."""
        response = client.post("/api/v1/containers/nonexistent-999/run-copilot-cycle")
        assert response.status_code == 200
        data = response.json()
        assert "error" in data

    @patch("app.scanner.background_scanner._last_scan_results", {
        "test-container-002": {
            "container_id": "test-container-002",
            "container_name": "test-app",
            "trust_score": 80.0,
            "risk_tier": "HEALTHY",
            "vector_scores": {"identity": 90.0, "configuration": 80.0, "network": 75.0, "resources": 85.0},
            "vector_reasons": {},
        }
    })
    def test_cycle_healthy_container_via_api(self) -> None:
        """Healthy container: API returns 200 with no_action_required."""
        response = client.post("/api/v1/containers/test-container-002/run-copilot-cycle")
        assert response.status_code == 200
        data = response.json()
        assert data["final_action"] == "no_action_required"
