"""Unit tests for the five trust vectors in ``app/trust_engine/vectors/``.

Each vector is a pure function over Docker API dicts, so every expected value
below is the vector's documented arithmetic worked through by hand — not a
snapshot of whatever the code happened to return.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.observability.mcp_client import MCPClientError
from app.trust_engine.vectors.configuration import score_configuration
from app.trust_engine.vectors.identity import score_identity
from app.trust_engine.vectors.llm_behavior import (
    COST_PER_HOUR_THRESHOLD,
    LATENCY_MS_THRESHOLD,
    score_llm_behavior,
)
from app.trust_engine.vectors.network import CRITICAL_PORTS, score_network
from app.trust_engine.vectors.resources import score_resources

from .conftest import make_inspect, make_stats


# ═════════════════════════════════════════════════════════════════════════════
# Identity — is the image sanctioned?
# ═════════════════════════════════════════════════════════════════════════════

class TestIdentityVector:
    @pytest.mark.parametrize(
        "image",
        [
            "nginx",
            "nginx:1.25",
            "postgres:16-alpine",
            "redis:7",
            "alpine:latest",
            "python:3.12-slim",
            "signoz/signoz-otel-collector:v0.128.2",
            "clickhouse/clickhouse-server:24.1.2-alpine",
            "otel/opentelemetry-collector:latest",
        ],
    )
    def test_sanctioned_images_score_100(self, image: str) -> None:
        """Whitelisted images — exact matches and glob matches alike — score 100."""
        score, reason = score_identity(make_inspect(image=image))
        assert score == 100.0
        assert "sanctioned whitelist" in reason

    @pytest.mark.parametrize(
        "image",
        [
            "shadow-ai/rogue-agent:latest",
            "randomuser/crypto-miner",
            "ghcr.io/unknown-org/unknown-tool:v2",
        ],
    )
    def test_unsanctioned_images_score_20(self, image: str) -> None:
        """An image nobody approved is the core Shadow AI signal: 20/100."""
        score, reason = score_identity(make_inspect(image=image))
        assert score == 20.0
        assert "NOT in the sanctioned whitelist" in reason

    def test_matching_is_case_insensitive(self) -> None:
        """Docker tags are case-sensitive but the whitelist check lowercases both sides."""
        assert score_identity(make_inspect(image="NGINX:LATEST"))[0] == 100.0

    def test_digest_only_image_scores_10(self) -> None:
        """``docker run <sha256:...>`` leaves no verifiable tag — the worst identity score.

        This is not hypothetical: it is exactly how the demo's CRITICAL container
        is built, because ``Config.Image`` is set to the literal digest string
        when a container is started by digest.
        """
        score, reason = score_identity(
            make_inspect(image="sha256:abcdef0123456789abcdef0123456789abcdef0123456789")
        )
        assert score == 10.0
        assert "no tag" in reason

    def test_missing_config_image_falls_back_to_digest_field(self) -> None:
        """With no ``Config.Image``, the top-level ``Image`` digest is used instead."""
        score, _ = score_identity(
            make_inspect(image=None, image_digest="sha256:deadbeefdeadbeefdeadbeef")
        )
        assert score == 10.0

    def test_empty_inspect_dict_does_not_raise(self) -> None:
        """A malformed/partial inspect payload must degrade, not explode."""
        score, _ = score_identity({})
        assert score == 10.0

    def test_registry_prefix_spoofing_is_not_caught(self) -> None:
        """KNOWN GAP, asserted so it cannot change silently.

        ``_is_sanctioned`` retries each pattern against the last path segment so
        that ``docker.io/library/nginx`` matches ``nginx``.  The side effect is
        that *any* registry host passes as long as the final segment is
        whitelisted — so an attacker's ``evil.example.com/nginx:latest`` scores a
        fully-trusted 100.

        Fixing this means matching the registry host too, which is a behaviour
        change beyond the scope of adding tests.  Until then this test documents
        the hole rather than pretending it is closed.
        """
        score, _ = score_identity(make_inspect(image="evil.example.com/nginx:latest"))
        assert score == 100.0, "if this now fails, the spoofing gap was fixed — update the test"


# ═════════════════════════════════════════════════════════════════════════════
# Configuration — root, privileged, read-only rootfs
# ═════════════════════════════════════════════════════════════════════════════

class TestConfigurationVector:
    def test_hardened_container_scores_100(self) -> None:
        """Non-root, unprivileged, no read-only bonus needed: baseline 100."""
        score, _ = score_configuration(make_inspect(user="appuser"))
        assert score == 100.0

    @pytest.mark.parametrize("user", ["", "0", "root"])
    def test_root_costs_25(self, user: str) -> None:
        """All three ways Docker can express "root" are penalised identically."""
        score, reason = score_configuration(make_inspect(user=user))
        assert score == 75.0
        assert "Running as root user (−25)" in reason

    def test_privileged_costs_40(self) -> None:
        score, reason = score_configuration(make_inspect(user="appuser", privileged=True))
        assert score == 60.0
        assert "Privileged mode ENABLED (−40)" in reason

    def test_root_and_privileged_stack_to_35(self) -> None:
        """100 − 25 − 40 = 35. This is the seed script's `privileged` profile."""
        score, _ = score_configuration(make_inspect(user="root", privileged=True))
        assert score == 35.0

    def test_readonly_rootfs_awards_15(self) -> None:
        """The bonus offsets penalties: root (75) + read-only rootfs (+15) = 90."""
        score, reason = score_configuration(
            make_inspect(user="root", readonly_rootfs=True)
        )
        assert score == 90.0
        assert "Read-only rootfs enabled (+15)" in reason

    def test_bonus_cannot_push_score_above_100(self) -> None:
        """A clean container with read-only rootfs would be 115 — clamped to 100."""
        score, _ = score_configuration(
            make_inspect(user="appuser", readonly_rootfs=True)
        )
        assert score == 100.0

    def test_missing_sections_default_to_root(self) -> None:
        """No ``Config``/``HostConfig`` means no evidence of a non-root user.

        The vector treats absence as root (the Docker default) rather than
        assuming the safe case — the right direction to fail in.
        """
        score, _ = score_configuration({})
        assert score == 75.0

    def test_score_never_leaves_0_100(self) -> None:
        for user in ("", "appuser"):
            for priv in (True, False):
                for ro in (True, False):
                    score, _ = score_configuration(
                        make_inspect(user=user, privileged=priv, readonly_rootfs=ro)
                    )
                    assert 0.0 <= score <= 100.0


# ═════════════════════════════════════════════════════════════════════════════
# Network — published port exposure
# ═════════════════════════════════════════════════════════════════════════════

class TestNetworkVector:
    def test_no_published_ports_scores_100(self) -> None:
        score, reason = score_network(make_inspect(port_bindings=None))
        assert score == 100.0
        assert "no network exposure" in reason

    def test_empty_port_bindings_dict_scores_100(self) -> None:
        assert score_network(make_inspect(port_bindings={}))[0] == 100.0

    def test_ordinary_port_on_all_interfaces_costs_15(self) -> None:
        score, reason = score_network(
            make_inspect(port_bindings={"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]})
        )
        assert score == 85.0
        assert "exposed on 0.0.0.0 (−15)" in reason

    @pytest.mark.parametrize("port", sorted(CRITICAL_PORTS))
    def test_critical_ports_cost_25_each(self, port: int) -> None:
        """SSH, Telnet, the Docker API and the common datastores are worth −25."""
        score, reason = score_network(
            make_inspect(
                port_bindings={f"{port}/tcp": [{"HostIp": "0.0.0.0", "HostPort": "39999"}]}
            )
        )
        assert score == 75.0
        assert "CRITICAL port" in reason

    @pytest.mark.parametrize("host_ip", ["127.0.0.1", "::1"])
    def test_loopback_bindings_are_free(self, host_ip: str) -> None:
        """Publishing to loopback only is not exposure — even for port 22."""
        score, reason = score_network(
            make_inspect(port_bindings={"22/tcp": [{"HostIp": host_ip, "HostPort": "2222"}]})
        )
        assert score == 100.0
        assert "local-only, safe" in reason

    @pytest.mark.parametrize("host_ip", ["", "0.0.0.0", "::"])
    def test_empty_host_ip_is_treated_as_all_interfaces(self, host_ip: str) -> None:
        """Docker leaves ``HostIp`` blank for ``-p 8080:8080``, which means 0.0.0.0.

        Reading blank as "unknown, therefore safe" would silently miss the most
        common way a port gets exposed.
        """
        score, _ = score_network(
            make_inspect(port_bindings={"8080/tcp": [{"HostIp": host_ip, "HostPort": "8080"}]})
        )
        assert score == 85.0

    def test_specific_non_loopback_ip_costs_10(self) -> None:
        """Binding to one LAN address is narrower than 0.0.0.0, so a smaller penalty."""
        score, _ = score_network(
            make_inspect(
                port_bindings={"8080/tcp": [{"HostIp": "192.168.1.10", "HostPort": "8080"}]}
            )
        )
        assert score == 90.0

    def test_penalties_accumulate_across_bindings(self) -> None:
        """One critical + two ordinary ports: 100 − 25 − 15 − 15 = 45."""
        score, _ = score_network(
            make_inspect(
                port_bindings={
                    "22/tcp": [{"HostIp": "0.0.0.0", "HostPort": "2222"}],
                    "8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}],
                    "9090/tcp": [{"HostIp": "0.0.0.0", "HostPort": "9090"}],
                }
            )
        )
        assert score == 45.0

    def test_score_floors_at_zero(self) -> None:
        """Four critical ports is −100; a fifth must not produce a negative score.

        The demo's CRITICAL container relies on this floor.
        """
        score, _ = score_network(
            make_inspect(
                port_bindings={
                    f"{port}/tcp": [{"HostIp": "0.0.0.0", "HostPort": f"3{port}"}]
                    for port in (22, 2375, 5432, 6379, 27017)
                }
            )
        )
        assert score == 0.0

    def test_multiple_host_bindings_for_one_container_port(self) -> None:
        """A single container port can map to several host bindings; each is scored."""
        score, _ = score_network(
            make_inspect(
                port_bindings={
                    "8080/tcp": [
                        {"HostIp": "0.0.0.0", "HostPort": "8080"},
                        {"HostIp": "0.0.0.0", "HostPort": "8081"},
                    ]
                }
            )
        )
        assert score == 70.0

    def test_declared_but_unpublished_port_is_free(self) -> None:
        """``EXPOSE`` without ``-p`` yields an empty binding list — not exposure."""
        assert score_network(make_inspect(port_bindings={"8080/tcp": []}))[0] == 100.0

    def test_unparseable_port_key_is_treated_as_non_critical(self) -> None:
        """A malformed key must not raise; it falls back to the −15 ordinary penalty."""
        score, _ = score_network(
            make_inspect(port_bindings={"not-a-port": [{"HostIp": "0.0.0.0", "HostPort": "1"}]})
        )
        assert score == 85.0

    def test_udp_critical_ports_are_scored_too(self) -> None:
        """The protocol suffix is stripped before the port is classified."""
        score, _ = score_network(
            make_inspect(port_bindings={"5432/udp": [{"HostIp": "0.0.0.0", "HostPort": "5432"}]})
        )
        assert score == 75.0


# ═════════════════════════════════════════════════════════════════════════════
# Resources — limits and live utilisation
# ═════════════════════════════════════════════════════════════════════════════

class TestResourcesVector:
    def test_both_limits_set_and_usage_low_scores_100(self) -> None:
        score, _ = score_resources(
            make_stats(cpu_percent=12.0, mem_percent=40.0), make_inspect()
        )
        assert score == 100.0

    def test_no_memory_limit_costs_20(self) -> None:
        score, reason = score_resources(
            make_stats(cpu_percent=5.0, mem_percent=10.0), make_inspect(memory=0)
        )
        assert score == 80.0
        assert "No memory limit set (−20)" in reason

    def test_no_cpu_limit_costs_15(self) -> None:
        score, reason = score_resources(
            make_stats(cpu_percent=5.0, mem_percent=10.0), make_inspect(nano_cpus=0)
        )
        assert score == 85.0
        assert "No CPU limit set (−15)" in reason

    def test_no_limits_at_all_scores_65(self) -> None:
        """100 − 20 − 15 = 65 — the seed script's `unbounded` and `privileged` profiles."""
        score, _ = score_resources(
            make_stats(cpu_percent=5.0, mem_percent=10.0),
            make_inspect(memory=0, nano_cpus=0),
        )
        assert score == 65.0

    def test_cpu_quota_also_counts_as_a_cpu_limit(self) -> None:
        """``--cpu-quota`` is an alternative to ``--cpus``; either satisfies the check."""
        score, reason = score_resources(
            make_stats(cpu_percent=5.0, mem_percent=10.0),
            make_inspect(nano_cpus=0, cpu_quota=50_000),
        )
        assert score == 100.0
        assert "CPU limit configured" in reason

    def test_cpu_above_80_percent_costs_20(self) -> None:
        score, reason = score_resources(
            make_stats(cpu_percent=95.0, mem_percent=10.0), make_inspect()
        )
        assert score == 80.0
        assert "> 80% threshold (−20)" in reason

    def test_cpu_exactly_at_80_percent_is_not_penalised(self) -> None:
        """The comparison is strictly ``> 80``, so the boundary itself is clean."""
        score, _ = score_resources(
            make_stats(cpu_percent=80.0, mem_percent=10.0), make_inspect()
        )
        assert score == 100.0

    def test_memory_above_80_percent_costs_20(self) -> None:
        score, reason = score_resources(
            make_stats(cpu_percent=5.0, mem_percent=90.0), make_inspect()
        )
        assert score == 80.0
        assert "Memory usage 90.0% > 80% threshold (−20)" in reason

    def test_worst_case_scores_25(self) -> None:
        """No limits plus both utilisations hot: 100 − 20 − 15 − 20 − 20 = 25."""
        score, _ = score_resources(
            make_stats(cpu_percent=99.0, mem_percent=99.0),
            make_inspect(memory=0, nano_cpus=0),
        )
        assert score == 25.0

    def test_demo_critical_resource_profile_scores_45(self) -> None:
        """The verified CRITICAL recipe's resources vector: no limits + CPU pegged.

        100 − 20 (no mem limit) − 15 (no CPU limit) − 20 (CPU >80%) = 45, with
        memory usage unavailable because an unlimited container reports the host
        total as its limit.
        """
        score, _ = score_resources(
            make_stats(cpu_percent=100.0), make_inspect(memory=0, nano_cpus=0)
        )
        assert score == 45.0

    def test_missing_stats_report_unavailable_rather_than_assuming(self) -> None:
        """With no stats snapshot, only the limit checks apply — no invented usage."""
        score, reason = score_resources({}, make_inspect())
        assert score == 100.0
        assert "CPU usage data unavailable" in reason
        assert "Memory usage data unavailable" in reason

    def test_zero_system_delta_does_not_divide_by_zero(self) -> None:
        """Two identical stats samples give a zero system delta — must yield None."""
        flat = {
            "cpu_stats": {"cpu_usage": {"total_usage": 500}, "system_cpu_usage": 1000, "online_cpus": 2},
            "precpu_stats": {"cpu_usage": {"total_usage": 500}, "system_cpu_usage": 1000},
        }
        score, reason = score_resources(flat, make_inspect())
        assert score == 100.0
        assert "CPU usage data unavailable" in reason

    def test_zero_memory_limit_in_stats_is_not_divided_by(self) -> None:
        """An unlimited container reports ``limit: 0``; that must not raise."""
        stats = {"memory_stats": {"usage": 12345, "limit": 0}}
        score, reason = score_resources(stats, make_inspect())
        assert score == 100.0
        assert "Memory usage data unavailable" in reason

    def test_cpu_percent_scales_with_core_count(self) -> None:
        """CPU% is per-host, not per-core: 50% of 4 cores is reported as 200%.

        A container saturating two of four cores is genuinely above the 80%
        threshold, and the multi-core multiplication is what makes that visible.
        """
        stats = make_stats(cpu_percent=200.0, online_cpus=4)
        score, reason = score_resources(stats, make_inspect())
        assert "200.0%" in reason
        assert score == 80.0


# ═════════════════════════════════════════════════════════════════════════════
# LLM behaviour — the only vector that needs SigNoz
# ═════════════════════════════════════════════════════════════════════════════

def _mcp_response(rows: list[dict[str, Any]], status: str = "success") -> dict[str, Any]:
    """Wrap trace rows in the nested envelope a real ``signoz_search_traces`` returns."""
    payload = {"status": status, "data": {"data": {"results": [{"rows": rows}]}}}
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


class _StubMCP:
    """Minimal stand-in for ``SentinelMCPClient.search_traces``."""

    def __init__(self, response: Any = None, raises: Exception | None = None) -> None:
        self._response = response
        self._raises = raises
        self.calls: list[dict[str, Any]] = []

    async def search_traces(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self._response


def _score_llm(stub: _StubMCP, name: str = "some-container") -> tuple[float, str]:
    """Run the async scorer synchronously so the suite needs no pytest-asyncio."""
    return asyncio.run(score_llm_behavior(name, stub))  # type: ignore[arg-type]


class TestLlmBehaviorVector:
    def test_neutral_100_when_no_llm_spans_found(self) -> None:
        """The headline guarantee: this vector never penalises a non-LLM container."""
        score, reason = _score_llm(_StubMCP(_mcp_response([])))
        assert score == 100.0
        assert "not applicable" in reason

    def test_neutral_100_when_signoz_returns_no_result_sets(self) -> None:
        """A successful query that matched nothing at all is still "not applicable"."""
        empty = {
            "content": [
                {"text": json.dumps({"status": "success", "data": {"data": {"results": []}}})}
            ]
        }
        assert _score_llm(_StubMCP(empty))[0] == 100.0

    def test_neutral_100_when_mcp_is_unreachable(self) -> None:
        """No SigNoz means "not measured", never "suspicious"."""
        score, reason = _score_llm(_StubMCP(raises=MCPClientError("no API key")))
        assert score == 100.0
        assert "not scored" in reason

    def test_non_llm_span_names_are_filtered_out(self) -> None:
        """Ordinary HTTP/DB spans must not be mistaken for LLM activity."""
        rows = [
            {"name": "GET /api/v1/containers", "durationNano": 5_000_000},
            {"name": "postgres.query", "durationNano": 1_000_000},
        ]
        assert _score_llm(_StubMCP(_mcp_response(rows)))[0] == 100.0

    @pytest.mark.parametrize(
        "span_name",
        [
            "llm.chat.completion",
            "gen_ai.chat",
            "openai.embeddings",
            "gemini.generate",
            "langchain.agent.run",
            "chat_completion",
            "llm_call",
        ],
    )
    def test_llm_span_names_are_recognised(self, span_name: str) -> None:
        """Detected LLM activity drops the vector from neutral 100 to a base of 80."""
        rows = [{"name": span_name, "durationNano": 1_000_000_000}]
        score, reason = _score_llm(_StubMCP(_mcp_response(rows)))
        assert score == 80.0
        assert "LLM activity detected: 1 span(s)" in reason

    def test_span_name_matching_is_case_insensitive(self) -> None:
        rows = [{"name": "OpenAI.ChatCompletion", "durationNano": 1_000_000_000}]
        assert _score_llm(_StubMCP(_mcp_response(rows)))[0] == 80.0

    def test_operation_name_field_is_also_read(self) -> None:
        """Some SigNoz responses key the span name as ``operationName``."""
        rows = [{"operationName": "gen_ai.chat", "durationNano": 1_000_000_000}]
        assert _score_llm(_StubMCP(_mcp_response(rows)))[0] == 80.0

    def test_high_latency_costs_20(self) -> None:
        """Slow LLM calls suggest recursive agent chains: 80 − 20 = 60."""
        over = int((LATENCY_MS_THRESHOLD + 1_000) * 1_000_000)
        rows = [{"name": "llm.chat.completion", "durationNano": over}]
        score, reason = _score_llm(_StubMCP(_mcp_response(rows)))
        assert score == 60.0
        assert "(−20)" in reason

    def test_low_token_usage_earns_a_bonus(self) -> None:
        """Under 500 tokens is a well-controlled agent: 80 + 10 = 90."""
        rows = [
            {
                "name": "llm.chat.completion",
                "durationNano": 1_000_000_000,
                "gen_ai.usage.total_tokens": 120,
            }
        ]
        score, reason = _score_llm(_StubMCP(_mcp_response(rows)))
        assert score == 90.0
        assert "well-controlled (+10)" in reason

    def test_high_estimated_cost_costs_30(self) -> None:
        """A large token count over short calls extrapolates past the $/hr threshold.

        The estimate is a rough proxy, not billing data — see the vector's own
        docstring. This test pins the arithmetic, not the dollar accuracy.
        """
        rows = [
            {
                "name": "llm.chat.completion",
                "durationNano": 1_000_000_000,
                "gen_ai.usage.total_tokens": 1_000_000,
            }
        ]
        score, reason = _score_llm(_StubMCP(_mcp_response(rows)))
        assert score == 50.0
        assert f"${COST_PER_HOUR_THRESHOLD}/hr threshold (−30)" in reason

    def test_average_latency_is_averaged_across_spans(self) -> None:
        """Two spans of 1s and 9s average to 5s — exactly on the threshold, so clean."""
        rows = [
            {"name": "llm_call", "durationNano": 1_000_000_000},
            {"name": "llm_call", "durationNano": 9_000_000_000},
        ]
        score, reason = _score_llm(_StubMCP(_mcp_response(rows)))
        assert "Avg LLM latency 5000ms" in reason
        assert score == 80.0

    def test_token_counts_accumulate_across_attribute_keys(self) -> None:
        rows = [
            {
                "name": "gen_ai.chat",
                "durationNano": 1_000_000_000,
                "gen_ai.usage.input_tokens": 100,
                "gen_ai.usage.output_tokens": 200,
            }
        ]
        score, reason = _score_llm(_StubMCP(_mcp_response(rows)))
        assert "300 total" in reason
        assert score == 90.0

    def test_non_numeric_token_value_is_ignored(self) -> None:
        """A malformed attribute must not abort scoring."""
        rows = [
            {
                "name": "gen_ai.chat",
                "durationNano": 1_000_000_000,
                "gen_ai.usage.total_tokens": "not-a-number",
            }
        ]
        assert _score_llm(_StubMCP(_mcp_response(rows)))[0] == 80.0

    @pytest.mark.parametrize(
        "response",
        [
            {},
            {"content": []},
            {"content": [{"text": "this is not json"}]},
            {"content": [{"text": '{"status": "error"}'}]},
        ],
        ids=["empty-dict", "no-content", "bad-json", "error-status"],
    )
    def test_unusable_responses_fall_back_to_neutral(self, response: dict[str, Any]) -> None:
        """Every malformed-response path returns the neutral score, not an exception."""
        assert _score_llm(_StubMCP(response))[0] == 100.0

    def test_container_name_is_passed_through_as_service_name(self) -> None:
        stub = _StubMCP(_mcp_response([]))
        _score_llm(stub, name="sentinel-demo-clean")
        assert stub.calls[0]["service_name"] == "sentinel-demo-clean"
