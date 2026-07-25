"""Unit tests for the FastAPI routes in ``app/api/routes.py``.

The routes are a thin, side-effect-free read layer over the scanner's in-memory
store, so they are driven by seeding that store directly.  The three places a
route reaches outside itself — ``kill_container``, ``Investigator`` and
``run_copilot_cycle`` — are patched, which is also how the error paths (503 on
an unreachable daemon, 500 on an investigation failure) get exercised at all:
they are unreachable from a healthy live system.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.models.schemas import AuditLogEntry, InvestigationResult, append_audit_entry

from .conftest import make_scan_result

UNSANCTIONED_REASONS = {
    "identity": "Image 'shadow-ai/agent' is NOT in the sanctioned whitelist — unsanctioned identity",
    "configuration": "Running as root user (−25); Privileged mode ENABLED (−40) — full host access",
    "network": "CRITICAL port 22→2222 exposed on 0.0.0.0 (−25)",
    "resources": "No memory limit set (−20) — OOM risk",
    "llm_behavior": "No LLM activity detected — not applicable",
}

RISKY_VECTORS = {
    "identity": 20.0,
    "configuration": 35.0,
    "network": 0.0,
    "resources": 65.0,
    "llm_behavior": 100.0,
}


def seed(store: dict[str, Any], *entries: dict[str, Any]) -> None:
    for entry in entries:
        store[entry["container_id"]] = entry


def healthy(cid: str = "aaa111", name: str = "sentinel-demo-clean") -> dict[str, Any]:
    return make_scan_result(cid, name, 100.0, "HEALTHY")


def critical(cid: str = "ccc333", name: str = "sentinel-crit-test") -> dict[str, Any]:
    return make_scan_result(cid, name, 38.0, "CRITICAL", RISKY_VECTORS, UNSANCTIONED_REASONS)


def high_risk(cid: str = "bbb222", name: str = "sentinel-demo-privileged") -> dict[str, Any]:
    return make_scan_result(cid, name, 43.5, "HIGH RISK", RISKY_VECTORS, UNSANCTIONED_REASONS)


def elevated(cid: str = "ddd444", name: str = "sentinel-demo-exposed") -> dict[str, Any]:
    return make_scan_result(cid, name, 64.0, "ELEVATED")


# ═════════════════════════════════════════════════════════════════════════════
# GET /containers
# ═════════════════════════════════════════════════════════════════════════════

class TestListContainers:
    def test_empty_store_returns_empty_list(self, client: TestClient) -> None:
        """Before the first scan completes the API is empty, not an error."""
        response = client.get("/api/v1/containers")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_every_scanned_container(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        seed(scan_store, healthy(), critical())
        body = client.get("/api/v1/containers").json()
        assert len(body) == 2
        assert {c["container_name"] for c in body} == {
            "sentinel-demo-clean",
            "sentinel-crit-test",
        }

    def test_entries_carry_the_full_vector_breakdown(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        """The frontend and the demo narration both depend on reasons, not just scores."""
        seed(scan_store, critical())
        entry = client.get("/api/v1/containers").json()[0]
        assert entry["trust_score"] == 38.0
        assert entry["risk_tier"] == "CRITICAL"
        assert set(entry["vector_scores"]) == {
            "identity",
            "configuration",
            "network",
            "resources",
            "llm_behavior",
        }
        assert "NOT in the sanctioned whitelist" in entry["vector_reasons"]["identity"]


class TestGetContainerDetail:
    def test_known_container_returns_its_scan_result(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        seed(scan_store, high_risk())
        body = client.get("/api/v1/containers/bbb222").json()
        assert body["container_name"] == "sentinel-demo-privileged"
        assert body["trust_score"] == 43.5

    def test_unknown_container_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/containers/does-not-exist")
        assert response.status_code == 404
        assert "not found in scan results" in response.json()["detail"]


# ═════════════════════════════════════════════════════════════════════════════
# Kill switch — the manual, human-triggered path
# ═════════════════════════════════════════════════════════════════════════════

class TestKillContainer:
    def test_successful_kill(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            routes, "kill_container", lambda cid: (calls.append(cid), True)[1]
        )
        body = client.post("/api/v1/containers/ccc333/kill").json()
        assert body["success"] is True
        assert calls == ["ccc333"], "the container id must be forwarded verbatim"

    def test_failed_kill_is_200_with_success_false(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A container that was already gone is a reportable outcome, not a server error.

        The frontend renders ``success`` rather than branching on status code, so
        turning this into a 5xx would surface as a crash in the UI.
        """
        monkeypatch.setattr(routes, "kill_container", lambda cid: False)
        response = client.post("/api/v1/containers/ccc333/kill")
        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "may already be stopped" in response.json()["message"]

    def test_unreachable_docker_daemon_returns_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(_cid: str) -> bool:
            raise ConnectionError("Unable to connect to Docker daemon")

        monkeypatch.setattr(routes, "kill_container", boom)
        response = client.post("/api/v1/containers/ccc333/kill")
        assert response.status_code == 503
        assert "Docker daemon unreachable" in response.json()["detail"]

    def test_unexpected_error_returns_500(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(_cid: str) -> bool:
            raise RuntimeError("something else entirely")

        monkeypatch.setattr(routes, "kill_container", boom)
        response = client.post("/api/v1/containers/ccc333/kill")
        assert response.status_code == 500
        assert "Error killing container" in response.json()["detail"]

    @pytest.mark.parametrize("method", ["get", "post"])
    def test_governance_terminate_wraps_the_kill_endpoint(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, method: str
    ) -> None:
        """The frontend-compatible alias accepts both verbs and shares the same logic."""
        monkeypatch.setattr(routes, "kill_container", lambda cid: True)
        response = getattr(client, method)("/api/v1/governance/terminate/ccc333")
        assert response.status_code == 200
        assert response.json()["success"] is True


# ═════════════════════════════════════════════════════════════════════════════
# Investigation
# ═════════════════════════════════════════════════════════════════════════════

class _FakeInvestigator:
    """Stand-in for ``Investigator``: an async context manager with ``investigate``."""

    def __init__(self, raises: Exception | None = None) -> None:
        self._raises = raises
        self.kwargs: dict[str, Any] = {}
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> _FakeInvestigator:
        self.entered = True
        return self

    async def __aexit__(self, *_args: Any) -> None:
        self.exited = True

    async def investigate(self, **kwargs: Any) -> InvestigationResult:
        self.kwargs = kwargs
        if self._raises is not None:
            raise self._raises
        return InvestigationResult(
            container_id=kwargs["container_id"],
            container_name=kwargs["container_name"],
            trust_score=kwargs["trust_score"],
            risk_tier="CRITICAL",
            primary_vector="network",
            primary_cause="network (0/100): CRITICAL port 22→2222 exposed on 0.0.0.0 (−25)",
            summary="Container is CRITICAL.",
            alert_created=True,
            alert_name="Sentinel: Low Trust Score — sentinel-crit-test",
        )


class TestInvestigation:
    def test_investigation_returns_a_structured_result(
        self, client: TestClient, scan_store: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seed(scan_store, critical())
        fake = _FakeInvestigator()
        monkeypatch.setattr(routes, "Investigator", lambda: fake)

        body = client.get("/api/v1/containers/ccc333/investigation").json()

        assert body["primary_vector"] == "network"
        assert body["alert_created"] is True
        assert body["supporting_evidence"] == []
        assert body["investigated_at"], "the response model stamps its own timestamp"

    def test_scan_data_is_passed_through_to_the_investigator(
        self, client: TestClient, scan_store: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The route must hand over the stored vectors, not re-derive or drop them."""
        seed(scan_store, critical())
        fake = _FakeInvestigator()
        monkeypatch.setattr(routes, "Investigator", lambda: fake)

        client.get("/api/v1/containers/ccc333/investigation")

        assert fake.kwargs["container_name"] == "sentinel-crit-test"
        assert fake.kwargs["trust_score"] == 38.0
        assert fake.kwargs["vector_scores"] == RISKY_VECTORS
        assert fake.kwargs["vector_reasons"] == UNSANCTIONED_REASONS

    def test_context_manager_is_closed_even_on_success(
        self, client: TestClient, scan_store: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The MCP session must be released; a leak would exhaust connections."""
        seed(scan_store, critical())
        fake = _FakeInvestigator()
        monkeypatch.setattr(routes, "Investigator", lambda: fake)
        client.get("/api/v1/containers/ccc333/investigation")
        assert fake.entered and fake.exited

    def test_unknown_container_returns_404_before_any_mcp_work(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def should_not_run() -> _FakeInvestigator:
            raise AssertionError("Investigator must not be constructed for unknown ids")

        monkeypatch.setattr(routes, "Investigator", should_not_run)
        response = client.get("/api/v1/containers/nope/investigation")
        assert response.status_code == 404
        assert "background scanner" in response.json()["detail"]

    def test_investigation_failure_returns_500(
        self, client: TestClient, scan_store: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seed(scan_store, critical())
        monkeypatch.setattr(
            routes, "Investigator", lambda: _FakeInvestigator(raises=RuntimeError("MCP down"))
        )
        response = client.get("/api/v1/containers/ccc333/investigation")
        assert response.status_code == 500
        assert "Investigation failed" in response.json()["detail"]


class TestCopilotCycle:
    def test_cycle_summary_is_returned_verbatim(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        summary = {
            "container_id": "ccc333",
            "container_name": "sentinel-crit-test",
            "trust_score": 38.0,
            "risk_tier": "CRITICAL",
            "steps_executed": ["investigate", "remediate"],
            "final_action": "killed",
        }

        async def fake_cycle(cid: str) -> dict[str, Any]:
            assert cid == "ccc333"
            return summary

        monkeypatch.setattr(routes, "run_copilot_cycle", fake_cycle)
        response = client.post("/api/v1/containers/ccc333/run-copilot-cycle")
        assert response.status_code == 200
        assert response.json() == summary

    def test_cycle_failure_returns_500(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(_cid: str) -> dict[str, Any]:
            raise RuntimeError("docker gone")

        monkeypatch.setattr(routes, "run_copilot_cycle", boom)
        response = client.post("/api/v1/containers/zzz/run-copilot-cycle")
        assert response.status_code == 500
        assert "Copilot cycle failed" in response.json()["detail"]


# ═════════════════════════════════════════════════════════════════════════════
# GET /metrics/summary
# ═════════════════════════════════════════════════════════════════════════════

class TestMetricsSummary:
    def test_empty_fleet_reports_zeroes_not_nan(self, client: TestClient) -> None:
        """``sum([]) / 0`` would raise; the route must guard the empty case."""
        body = client.get("/api/v1/metrics/summary").json()
        assert body["total_containers"] == 0
        assert body["average_trust_score"] == 0.0
        assert body["threat_level"] == "LOW"

    def test_average_is_rounded_to_one_decimal(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        seed(scan_store, healthy(), critical())  # (100.0 + 38.0) / 2
        assert client.get("/api/v1/metrics/summary").json()["average_trust_score"] == 69.0

    def test_tier_counts(self, client: TestClient, scan_store: dict[str, Any]) -> None:
        seed(scan_store, healthy(), critical(), high_risk(), elevated())
        body = client.get("/api/v1/metrics/summary").json()
        assert body["total_containers"] == 4
        assert body["critical_risks"] == 1
        assert body["high_risks"] == 1

    @pytest.mark.parametrize(
        "entries,expected",
        [
            ([healthy()], "LOW"),
            ([healthy(), elevated()], "ELEVATED"),
            ([healthy(), elevated(), high_risk()], "HIGH"),
            ([healthy(), elevated(), high_risk(), critical()], "CRITICAL"),
        ],
        ids=["all-healthy", "worst-elevated", "worst-high", "worst-critical"],
    )
    def test_threat_level_reflects_the_worst_container(
        self,
        client: TestClient,
        scan_store: dict[str, Any],
        entries: list[dict[str, Any]],
        expected: str,
    ) -> None:
        """Fleet threat level is a max, not an average — one CRITICAL dominates."""
        seed(scan_store, *entries)
        assert client.get("/api/v1/metrics/summary").json()["threat_level"] == expected

    def test_money_saved_is_a_placeholder_model_not_measured_spend(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        """Pins the formula so nobody mistakes it for observed cost.

        ``money_saved = critical × $300 + high × $150`` is a hardcoded estimate
        in ``routes.py``; no cost metric is collected anywhere in the system.
        The UI marks it "Demo Data" and the SigNoz dashboards deliberately omit
        any cost-per-day panel. This test exists to keep that honest — if the
        number ever becomes real, it should stop matching this arithmetic.
        """
        seed(scan_store, critical(), high_risk())
        assert client.get("/api/v1/metrics/summary").json()["money_saved"] == 450


# ═════════════════════════════════════════════════════════════════════════════
# GET /discovery/shadow-ai
# ═════════════════════════════════════════════════════════════════════════════

class TestDiscovery:
    def test_sanctioned_flag_follows_the_identity_vector(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        """``is_sanctioned`` is identity ≥ 80 — the Shadow AI signal the UI keys on."""
        seed(scan_store, healthy(), critical())
        by_name = {c["name"]: c for c in client.get("/api/v1/discovery/shadow-ai").json()}
        assert by_name["sentinel-demo-clean"]["is_sanctioned"] is True
        assert by_name["sentinel-crit-test"]["is_sanctioned"] is False

    def test_trust_score_is_rounded_for_display(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        seed(scan_store, make_scan_result("e1", "svc", 68.4999, "ELEVATED"))
        assert client.get("/api/v1/discovery/shadow-ai").json()[0]["trust_score"] == 68.5

    def test_empty_store_returns_empty_list(self, client: TestClient) -> None:
        assert client.get("/api/v1/discovery/shadow-ai").json() == []


# ═════════════════════════════════════════════════════════════════════════════
# GET /security/alerts
# ═════════════════════════════════════════════════════════════════════════════

class TestSecurityAlerts:
    def test_only_critical_and_high_risk_generate_alerts(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        """ELEVATED and HEALTHY containers must not create alert noise."""
        seed(scan_store, healthy(), elevated(), high_risk(), critical())
        alerts = client.get("/api/v1/security/alerts").json()
        assert {a["agentName"] for a in alerts} == {
            "sentinel-demo-privileged",
            "sentinel-crit-test",
        }

    def test_severity_and_recommended_action_map_from_the_tier(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        """CRITICAL recommends a kill; HIGH RISK only recommends investigating.

        This mirrors the Remediator's own gate — the API must not suggest an
        action the autonomous path would refuse to take.
        """
        seed(scan_store, high_risk(), critical())
        by_name = {a["agentName"]: a for a in client.get("/api/v1/security/alerts").json()}

        assert by_name["sentinel-crit-test"]["severity"] == "critical"
        assert by_name["sentinel-crit-test"]["recommended_action"] == "kill"
        assert by_name["sentinel-demo-privileged"]["severity"] == "high"
        assert by_name["sentinel-demo-privileged"]["recommended_action"] == "investigate"

    def test_description_is_built_from_the_vector_reasons(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        """An alert has to say *why*, not just restate the score."""
        seed(scan_store, critical())
        alert = client.get("/api/v1/security/alerts").json()[0]
        assert "Privileged mode ENABLED" in alert["description"]
        assert "CRITICAL port 22" in alert["description"]
        assert alert["violationType"] == "CRITICAL — Trust Score 38"

    def test_description_falls_back_when_no_reason_matches(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        """With unrecognised reason text the alert still describes the container."""
        seed(
            scan_store,
            make_scan_result(
                "f1", "odd", 30.0, "CRITICAL", RISKY_VECTORS, {"identity": "unusual finding"}
            ),
        )
        alert = client.get("/api/v1/security/alerts").json()[0]
        assert alert["description"] == "Container scored 30 (CRITICAL)"

    def test_empty_store_produces_no_alerts(self, client: TestClient) -> None:
        assert client.get("/api/v1/security/alerts").json() == []


# ═════════════════════════════════════════════════════════════════════════════
# GET /governance/audit-logs
# ═════════════════════════════════════════════════════════════════════════════

class TestAuditLogs:
    def test_remediator_entries_are_returned_newest_first(self, client: TestClient) -> None:
        for i, action in enumerate(("skipped", "autonomous_kill")):
            append_audit_entry(
                AuditLogEntry(
                    timestamp=f"2026-07-25T10:0{i}:00+00:00",
                    container_id=f"cid{i}0000000",
                    container_name=f"container-{i}",
                    trust_score=38.0,
                    risk_tier="CRITICAL",
                    action=action,
                    reason="…",
                )
            )
        body = client.get("/api/v1/governance/audit-logs").json()
        assert [e["action"] for e in body] == ["autonomous_kill", "skipped"]
        assert all(e["tool"] == "remediator" for e in body)

    def test_entry_details_include_score_and_tier(self, client: TestClient) -> None:
        append_audit_entry(
            AuditLogEntry(
                container_id="ccc333",
                container_name="sentinel-crit-test",
                trust_score=38.0,
                risk_tier="CRITICAL",
                action="autonomous_kill",
                reason="Autonomously killed — root cause: network",
            )
        )
        entry = client.get("/api/v1/governance/audit-logs").json()[0]
        assert entry["details"].startswith("trust=38 [CRITICAL]:")
        assert "Autonomously killed" in entry["details"]

    def test_skips_are_audited_too(self, client: TestClient) -> None:
        """A decision *not* to act must be as reviewable as a kill."""
        append_audit_entry(
            AuditLogEntry(
                container_id="bbb222",
                container_name="sentinel-demo-privileged",
                trust_score=43.5,
                risk_tier="HIGH RISK",
                action="skipped",
                reason="Risk tier is 'HIGH RISK' — autonomous kill requires 'CRITICAL'.",
            )
        )
        entry = client.get("/api/v1/governance/audit-logs").json()[0]
        assert entry["action"] == "skipped"
        assert "requires 'CRITICAL'" in entry["details"]

    def test_falls_back_to_scanner_entries_when_no_action_has_fired(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        """With an empty audit log the endpoint shows scan activity instead of nothing."""
        seed(scan_store, healthy())
        body = client.get("/api/v1/governance/audit-logs").json()
        assert len(body) == 1
        assert body[0]["tool"] == "background_scanner"
        assert body[0]["action"] == "trust_scan → HEALTHY (100)"
        assert "id=100 cfg=100 net=100 res=100" in body[0]["details"]

    def test_real_entries_suppress_the_fallback(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        """Once the Remediator has acted, scanner pass-throughs must not dilute the trail."""
        seed(scan_store, healthy(), critical())
        append_audit_entry(
            AuditLogEntry(
                container_id="ccc333",
                container_name="sentinel-crit-test",
                trust_score=38.0,
                risk_tier="CRITICAL",
                action="autonomous_kill",
                reason="killed",
            )
        )
        body = client.get("/api/v1/governance/audit-logs").json()
        assert len(body) == 1
        assert body[0]["tool"] == "remediator"

    def test_limit_is_applied(self, client: TestClient) -> None:
        for i in range(5):
            append_audit_entry(
                AuditLogEntry(
                    timestamp=f"2026-07-25T10:0{i}:00+00:00",
                    container_id=f"cid{i}0000000",
                    container_name=f"container-{i}",
                    trust_score=10.0,
                    risk_tier="CRITICAL",
                    action="autonomous_kill",
                    reason="…",
                )
            )
        assert len(client.get("/api/v1/governance/audit-logs?limit=2").json()) == 2

    def test_empty_everything_returns_empty_list(self, client: TestClient) -> None:
        assert client.get("/api/v1/governance/audit-logs").json() == []


# ═════════════════════════════════════════════════════════════════════════════
# GET /metrics/cost
# ═════════════════════════════════════════════════════════════════════════════

class TestMetricsCost:
    def test_cost_is_derived_from_container_count_not_observed_spend(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        """Every figure here is ``count × $300``. Pinned so it cannot be mistaken for real.

        There is no cost metric anywhere in the pipeline — see ARCHITECTURE.md
        → "Cost figures are not measured".
        """
        seed(scan_store, healthy(), elevated(), critical())
        body = client.get("/api/v1/metrics/cost").json()
        assert body["totalSpend"] == 900
        assert body["totalSaved"] == 300  # one CRITICAL × $300
        assert body["savingsPercent"] == pytest.approx(33.3)
        assert body["projectedMonthly"] == 900

    def test_empty_fleet_does_not_divide_by_zero(self, client: TestClient) -> None:
        body = client.get("/api/v1/metrics/cost").json()
        assert body["totalSpend"] == 0
        assert body["burnRate"] == 0
        assert body["savingsPercent"] == 0.0

    def test_agent_costs_are_capped_at_five_entries(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        seed(scan_store, *(make_scan_result(f"c{i}", f"svc-{i}", 90.0, "HEALTHY") for i in range(8)))
        assert len(client.get("/api/v1/metrics/cost").json()["agentCosts"]) == 5

    def test_daily_burn_always_has_seven_points(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        """The chart expects a fixed 7-day window even with a single container."""
        seed(scan_store, healthy())
        assert len(client.get("/api/v1/metrics/cost").json()["dailyBurn"]) == 7


# ═════════════════════════════════════════════════════════════════════════════
# GET /system/health
# ═════════════════════════════════════════════════════════════════════════════

class TestSystemHealth:
    def test_no_containers_reports_no_containers(self, client: TestClient) -> None:
        body = client.get("/api/v1/system/health").json()
        assert body["status"] == "no_containers"
        assert body["total_containers"] == 0
        assert body["average_trust_score"] == 0

    def test_populated_fleet_reports_operational(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        seed(scan_store, healthy(), critical())
        body = client.get("/api/v1/system/health").json()
        assert body["status"] == "operational"
        assert body["total_containers"] == 2
        assert body["critical_containers"] == 1
        assert body["healthy_containers"] == 1
        assert body["average_trust_score"] == 69.0

    def test_timestamp_is_iso8601_utc(
        self, client: TestClient, scan_store: dict[str, Any]
    ) -> None:
        from datetime import datetime

        seed(scan_store, healthy())
        stamp = client.get("/api/v1/system/health").json()["timestamp"]
        assert datetime.fromisoformat(stamp).tzinfo is not None
