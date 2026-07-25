"""Unit tests for ``app/trust_engine/scorer.py``.

The scorer is the one place where the five vectors become a single number and a
tier, so it is where a silent weighting change would do the most damage: every
dashboard, alert threshold, and the autonomous kill gate all key off its output.

The ``TestVerifiedFleetProfiles`` class below is the important part — those five
vector sets and their expected totals were captured from a live run of
``scripts/seed_demo_agents.sh`` against a real Docker host, so they lock the
weights to numbers that were observed, not just derived.
"""

from __future__ import annotations

import pytest

from app.trust_engine.scorer import VECTOR_WEIGHTS, calculate_trust_score


def _vectors(
    identity: float = 100.0,
    configuration: float = 100.0,
    network: float = 100.0,
    resources: float = 100.0,
    llm_behavior: float = 100.0,
) -> dict[str, float]:
    return {
        "identity": identity,
        "configuration": configuration,
        "network": network,
        "resources": resources,
        "llm_behavior": llm_behavior,
    }


# ═════════════════════════════════════════════════════════════════════════════
# Weights
# ═════════════════════════════════════════════════════════════════════════════

class TestWeights:
    def test_weights_sum_to_one(self) -> None:
        """If these stop summing to 1.0, every score silently shifts scale."""
        assert sum(VECTOR_WEIGHTS.values()) == pytest.approx(1.0)

    def test_documented_weights(self) -> None:
        """Pinned against ARCHITECTURE.md and the dashboard panel descriptions."""
        assert VECTOR_WEIGHTS == {
            "identity": 0.25,
            "configuration": 0.25,
            "network": 0.15,
            "resources": 0.15,
            "llm_behavior": 0.20,
        }

    @pytest.mark.parametrize("vector,weight", sorted(VECTOR_WEIGHTS.items()))
    def test_each_vector_contributes_exactly_its_weight(
        self, vector: str, weight: float
    ) -> None:
        """Zeroing one vector must cost exactly ``weight × 100`` points.

        This is a stronger check than asserting the total: it proves the weight
        is actually applied to the vector it is named after, which a transposed
        dict would otherwise pass.
        """
        score, _ = calculate_trust_score({**_vectors(), vector: 0.0})
        assert score == pytest.approx(100.0 - weight * 100.0)


# ═════════════════════════════════════════════════════════════════════════════
# Verified fleet profiles — regression locks from a live run
# ═════════════════════════════════════════════════════════════════════════════

class TestVerifiedFleetProfiles:
    """Vector sets observed on a real Docker host, with their observed totals."""

    def test_clean_container(self) -> None:
        """``sentinel-demo-clean``: sanctioned, non-root, no ports, limits set."""
        assert calculate_trust_score(_vectors()) == (100.0, "HEALTHY")

    def test_unbounded_container(self) -> None:
        """``sentinel-demo-unbounded``: unsanctioned image, root, no limits.

        20(.25) + 75(.25) + 100(.15) + 65(.15) + 100(.20)
        = 5 + 18.75 + 15 + 9.75 + 20 = 68.50
        """
        score, tier = calculate_trust_score(
            _vectors(identity=20, configuration=75, network=100, resources=65)
        )
        assert score == pytest.approx(68.5)
        assert tier == "ELEVATED"

    def test_exposed_container(self) -> None:
        """``sentinel-demo-exposed``: unsanctioned, root, critical ports published.

        20(.25) + 75(.25) + 35(.15) + 100(.15) + 100(.20)
        = 5 + 18.75 + 5.25 + 15 + 20 = 64.00
        """
        score, tier = calculate_trust_score(
            _vectors(identity=20, configuration=75, network=35, resources=100)
        )
        assert score == pytest.approx(64.0)
        assert tier == "ELEVATED"

    def test_privileged_container(self) -> None:
        """``sentinel-demo-privileged``: the worst *ordinary* misconfiguration.

        20(.25) + 35(.25) + 0(.15) + 65(.15) + 100(.20)
        = 5 + 8.75 + 0 + 9.75 + 20 = 43.50

        Note this lands in HIGH RISK, not CRITICAL — privileged + root + four
        exposed critical ports is still not enough to trigger an autonomous
        kill, because ``llm_behavior``'s neutral 100 contributes a fixed 20
        points. That floor is why the demo needs a digest-only image.
        """
        score, tier = calculate_trust_score(
            _vectors(identity=20, configuration=35, network=0, resources=65)
        )
        assert score == pytest.approx(43.5)
        assert tier == "HIGH RISK"

    def test_critical_container(self) -> None:
        """``sentinel-crit-test``: digest-only image + privileged + ports + CPU abuse.

        10(.25) + 35(.25) + 0(.15) + 45(.15) + 100(.20)
        = 2.5 + 8.75 + 0 + 6.75 + 20 = 38.00

        The container that was actually killed autonomously in the recorded run.
        """
        score, tier = calculate_trust_score(
            _vectors(identity=10, configuration=35, network=0, resources=45)
        )
        assert score == pytest.approx(38.0)
        assert tier == "CRITICAL"


# ═════════════════════════════════════════════════════════════════════════════
# Tier boundaries
# ═════════════════════════════════════════════════════════════════════════════

class TestRiskTiers:
    @pytest.mark.parametrize(
        "uniform_score,expected_tier",
        [
            (0.0, "CRITICAL"),
            (39.9, "CRITICAL"),
            (40.0, "HIGH RISK"),
            (59.9, "HIGH RISK"),
            (60.0, "ELEVATED"),
            (79.9, "ELEVATED"),
            (80.0, "HEALTHY"),
            (100.0, "HEALTHY"),
        ],
    )
    def test_tier_boundaries_are_inclusive_at_the_bottom(
        self, uniform_score: float, expected_tier: float
    ) -> None:
        """Each threshold belongs to the *safer* tier: 40.0 is HIGH RISK, not CRITICAL.

        Off-by-one here would change which containers get killed, so the exact
        boundary behaviour is pinned rather than left implied.
        """
        score, tier = calculate_trust_score(
            _vectors(*(uniform_score,) * 5)
        )
        assert score == pytest.approx(uniform_score)
        assert tier == expected_tier

    def test_only_critical_is_below_the_kill_threshold(self) -> None:
        """The Remediator kills on tier, not score — these must stay in sync.

        ``remediator.py`` gates on ``risk_tier == "CRITICAL"`` while the alert
        rule created in SigNoz uses ``trust_score below 40``. If the CRITICAL
        threshold ever moves, the alert threshold has to move with it.
        """
        just_under, tier_under = calculate_trust_score(_vectors(*(39.99,) * 5))
        just_over, tier_over = calculate_trust_score(_vectors(*(40.0,) * 5))
        assert just_under < 40.0 and tier_under == "CRITICAL"
        assert just_over >= 40.0 and tier_over != "CRITICAL"


# ═════════════════════════════════════════════════════════════════════════════
# Missing / malformed input
# ═════════════════════════════════════════════════════════════════════════════

class TestMissingVectors:
    def test_missing_vector_weight_is_redistributed(self) -> None:
        """With only identity and configuration present, weight renormalises to 1.

        identity 0 + configuration 100 over a total weight of 0.5 → 50.0, not
        the 25.0 an un-normalised sum would give.
        """
        score, tier = calculate_trust_score({"identity": 0.0, "configuration": 100.0})
        assert score == pytest.approx(50.0)
        assert tier == "HIGH RISK"

    def test_single_vector_carries_the_whole_score(self) -> None:
        assert calculate_trust_score({"network": 42.0})[0] == pytest.approx(42.0)

    def test_no_vectors_fails_closed_to_critical(self) -> None:
        """No data must never read as healthy — an empty result is CRITICAL."""
        assert calculate_trust_score({}) == (0.0, "CRITICAL")

    def test_unknown_vector_names_are_ignored(self) -> None:
        """Only the five weighted vectors count; stray keys must not skew the total."""
        score, _ = calculate_trust_score({"identity": 100.0, "made_up_vector": 0.0})
        assert score == pytest.approx(100.0)

    def test_all_unknown_vectors_fails_closed(self) -> None:
        assert calculate_trust_score({"made_up_vector": 100.0}) == (0.0, "CRITICAL")

    def test_none_values_are_skipped_not_treated_as_zero(self) -> None:
        """The scorer's ``is not None`` check: a null vector drops out entirely."""
        score, _ = calculate_trust_score(
            {"identity": 100.0, "configuration": 100.0, "network": None}  # type: ignore[dict-item]
        )
        assert score == pytest.approx(100.0)


class TestClamping:
    def test_result_is_clamped_to_100(self) -> None:
        """Out-of-range vector input must not produce an impossible trust score."""
        assert calculate_trust_score(_vectors(*(150.0,) * 5))[0] == 100.0

    def test_result_is_clamped_to_0(self) -> None:
        assert calculate_trust_score(_vectors(*(-50.0,) * 5)) == (0.0, "CRITICAL")
