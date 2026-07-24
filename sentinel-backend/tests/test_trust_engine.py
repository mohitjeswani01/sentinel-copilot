"""
Sentinel Copilot — Trust Engine Vector & Scorer Tests.

At least 2 test cases per vector (healthy-case + risky-case) and
2 test cases for the scorer aggregation.
"""

import pytest

from app.trust_engine.vectors.identity import score_identity
from app.trust_engine.vectors.configuration import score_configuration
from app.trust_engine.vectors.network import score_network
from app.trust_engine.vectors.resources import score_resources
from app.trust_engine.scorer import calculate_trust_score


# ═══════════════════════════════════════════════════════════════════════════
# IDENTITY VECTOR
# ═══════════════════════════════════════════════════════════════════════════

class TestIdentityVector:
    """Tests for the identity vector scorer."""

    def test_sanctioned_image_scores_high(self) -> None:
        """A whitelisted image should receive a score of 100."""
        inspect = {"Config": {"Image": "nginx:latest"}}
        score, reason = score_identity(inspect)
        assert score == 100.0
        assert "sanctioned" in reason.lower()

    def test_unsanctioned_image_scores_low(self) -> None:
        """An unknown image should receive a score of 20."""
        inspect = {"Config": {"Image": "evil-crypto-miner:latest"}}
        score, reason = score_identity(inspect)
        assert score == 20.0
        assert "not in the sanctioned" in reason.lower()

    def test_digest_only_image_scores_very_low(self) -> None:
        """An image with only a sha256 digest (no tag) is unverifiable."""
        inspect = {"Config": {"Image": "sha256:abc123def456"}}
        score, reason = score_identity(inspect)
        assert score == 10.0
        assert "no tag" in reason.lower()


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION VECTOR
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigurationVector:
    """Tests for the configuration vector scorer."""

    def test_healthy_configuration(self) -> None:
        """A non-root, non-privileged container with readonly rootfs → high score."""
        inspect = {
            "Config": {"User": "appuser"},
            "HostConfig": {
                "Privileged": False,
                "ReadonlyRootfs": True,
            },
        }
        score, reason = score_configuration(inspect)
        # 100 (base) + 15 (readonly) = 115 → clamped to 100
        assert score == 100.0
        assert "non-root" in reason.lower()
        assert "read-only rootfs enabled" in reason.lower()

    def test_risky_root_privileged(self) -> None:
        """Root user + privileged mode → significant penalties."""
        inspect = {
            "Config": {"User": ""},
            "HostConfig": {
                "Privileged": True,
                "ReadonlyRootfs": False,
            },
        }
        score, reason = score_configuration(inspect)
        # 100 - 25 (root) - 40 (privileged) = 35
        assert score == 35.0
        assert "root" in reason.lower()
        assert "privileged" in reason.lower()


# ═══════════════════════════════════════════════════════════════════════════
# NETWORK VECTOR
# ═══════════════════════════════════════════════════════════════════════════

class TestNetworkVector:
    """Tests for the network vector scorer."""

    def test_no_ports_scores_perfect(self) -> None:
        """No port bindings → 100 (no network exposure)."""
        inspect = {"HostConfig": {"PortBindings": {}}}
        score, reason = score_network(inspect)
        assert score == 100.0
        assert "no port bindings" in reason.lower()

    def test_public_critical_port_scores_low(self) -> None:
        """SSH port exposed on 0.0.0.0 → heavy penalty."""
        inspect = {
            "HostConfig": {
                "PortBindings": {
                    "22/tcp": [{"HostIp": "0.0.0.0", "HostPort": "2222"}],
                }
            }
        }
        score, reason = score_network(inspect)
        # 100 - 25 (critical port on 0.0.0.0) = 75
        assert score == 75.0
        assert "critical port" in reason.lower()

    def test_localhost_binding_is_safe(self) -> None:
        """Ports bound to 127.0.0.1 should not cause a penalty."""
        inspect = {
            "HostConfig": {
                "PortBindings": {
                    "8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8080"}],
                }
            }
        }
        score, reason = score_network(inspect)
        assert score == 100.0
        assert "local-only" in reason.lower()


# ═══════════════════════════════════════════════════════════════════════════
# RESOURCES VECTOR
# ═══════════════════════════════════════════════════════════════════════════

class TestResourcesVector:
    """Tests for the resources vector scorer."""

    def test_healthy_resources(self) -> None:
        """Container with limits set and moderate usage → high score."""
        inspect = {
            "HostConfig": {
                "Memory": 512 * 1024 * 1024,  # 512 MB
                "NanoCpus": 1_000_000_000,      # 1 CPU
                "CpuPeriod": 0,
                "CpuQuota": 0,
            },
        }
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200_000_000},
                "system_cpu_usage": 10_000_000_000,
                "online_cpus": 4,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100_000_000},
                "system_cpu_usage": 9_000_000_000,
            },
            "memory_stats": {
                "usage": 200 * 1024 * 1024,  # 200 MB
                "limit": 512 * 1024 * 1024,  # 512 MB
            },
        }
        score, reason = score_resources(stats, inspect)
        # 100 (base), has mem limit (+0), has CPU limit via NanoCpus (+0),
        # CPU usage ~40% (+0), Mem usage ~39% (+0) = 100
        assert score == 100.0
        assert "within limits" in reason.lower()

    def test_risky_no_limits(self) -> None:
        """Container with no limits set → penalties."""
        inspect = {
            "HostConfig": {
                "Memory": 0,
                "NanoCpus": 0,
                "CpuPeriod": 0,
                "CpuQuota": 0,
            },
        }
        stats: dict = {}
        score, reason = score_resources(stats, inspect)
        # 100 - 20 (no mem limit) - 15 (no CPU limit) = 65
        assert score == 65.0
        assert "no memory limit" in reason.lower()
        assert "no cpu limit" in reason.lower()


# ═══════════════════════════════════════════════════════════════════════════
# SCORER (weighted aggregation)
# ═══════════════════════════════════════════════════════════════════════════

class TestScorer:
    """Tests for the trust score aggregation."""

    def test_all_healthy_vectors(self) -> None:
        """All vectors at 100 → Trust Score 100, HEALTHY tier."""
        vectors = {
            "identity": 100.0,
            "configuration": 100.0,
            "network": 100.0,
            "resources": 100.0,
        }
        score, tier = calculate_trust_score(vectors)
        assert score == 100.0
        assert tier == "HEALTHY"

    def test_critical_tier(self) -> None:
        """All vectors at 20 → Trust Score 20, CRITICAL tier."""
        vectors = {
            "identity": 20.0,
            "configuration": 20.0,
            "network": 20.0,
            "resources": 20.0,
        }
        score, tier = calculate_trust_score(vectors)
        assert score == 20.0
        assert tier == "CRITICAL"

    def test_mixed_scores_elevated(self) -> None:
        """Mixed scores should produce weighted average in ELEVATED range."""
        vectors = {
            "identity": 100.0,   # 30% → 30
            "configuration": 75.0,  # 30% → 22.5
            "network": 50.0,    # 20% → 10
            "resources": 65.0,  # 20% → 13
        }
        score, tier = calculate_trust_score(vectors)
        # Expected: 30 + 22.5 + 10 + 13 = 75.5
        assert abs(score - 75.5) < 0.1
        assert tier == "ELEVATED"

    def test_missing_vectors_redistribute(self) -> None:
        """Missing vectors should not distort the score — weights redistribute."""
        vectors = {
            "identity": 100.0,
            "configuration": 100.0,
        }
        score, tier = calculate_trust_score(vectors)
        # Only identity(30%) + configuration(30%) present → normalised to 100%
        assert score == 100.0
        assert tier == "HEALTHY"
