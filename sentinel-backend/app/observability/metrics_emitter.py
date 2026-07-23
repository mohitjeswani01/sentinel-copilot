"""
Sentinel Copilot Backend — Container Trust Metrics Emitter.

Emits OpenTelemetry gauge metrics for per-container trust scores and
individual trust-vector scores.  All metrics are exported to SigNoz via
the OTLP pipeline configured in ``otel_setup``.
"""

from __future__ import annotations

import logging
from typing import Any

from opentelemetry.metrics import Observation

from app.core.config import settings
from app.observability.otel_setup import get_meter

logger = logging.getLogger(__name__)


class SentinelMetricsEmitter:
    """Manages Sentinel trust-score gauge instruments and emits measurements.

    Gauges use **observable** (async) callbacks so the latest values are
    reported automatically each time the metric reader performs a collection
    cycle.  Call ``emit_container_trust_metrics`` whenever new scores are
    computed; the emitter caches the latest value per container.
    """

    def __init__(self) -> None:
        self._meter = get_meter("sentinel-trust-engine")

        # Internal cache: container_id → {metric_name: (value, attributes)}
        self._cache: dict[str, dict[str, tuple[float, dict[str, str]]]] = {}

        # ── Define observable gauges ─────────────────────────────────────
        self._gauge_names: list[str] = [
            "sentinel.container.trust_score",
            "sentinel.container.vector.identity",
            "sentinel.container.vector.configuration",
            "sentinel.container.vector.network",
            "sentinel.container.vector.resources",
            "sentinel.container.vector.llm_behavior",
        ]

        for gauge_name in self._gauge_names:
            self._meter.create_observable_gauge(
                name=gauge_name,
                callbacks=[self._make_callback(gauge_name)],
                description=f"Sentinel gauge: {gauge_name}",
                unit="score",
            )

        logger.info(
            "SentinelMetricsEmitter initialised with %d gauges",
            len(self._gauge_names),
        )

    # ── Callback factory ─────────────────────────────────────────────────

    def _make_callback(
        self,
        gauge_name: str,
    ):  # type: ignore[override]
        """Return an observable-gauge callback that yields cached values."""

        def _callback(_: Any) -> list[Observation]:
            observations: list[Observation] = []
            for _cid, metric_map in self._cache.items():
                entry = metric_map.get(gauge_name)
                if entry is not None:
                    value, attrs = entry
                    observations.append(Observation(value=value, attributes=attrs))
            return observations

        return _callback

    # ── Public API ───────────────────────────────────────────────────────

    def emit_container_trust_metrics(
        self,
        container_id: str,
        container_name: str,
        trust_score: float,
        vector_scores: dict[str, float],
    ) -> None:
        """Record trust metrics for a container.

        The values are cached internally and reported on the next OTel
        metric collection cycle.

        Args:
            container_id: Short or full Docker container ID.
            container_name: Human-readable container name.
            trust_score: Overall trust score (0–100).
            vector_scores: Mapping of vector names to their scores
                (``identity``, ``configuration``, ``network``,
                ``resources``, ``llm_behavior``).  Values 0–100.
        """
        attrs: dict[str, str] = {
            "container_id": container_id,
            "container_name": container_name,
            "environment": settings.ENVIRONMENT,
        }

        metric_map: dict[str, tuple[float, dict[str, str]]] = {
            "sentinel.container.trust_score": (
                _clamp(trust_score),
                attrs,
            ),
        }

        _vector_key_to_gauge = {
            "identity": "sentinel.container.vector.identity",
            "configuration": "sentinel.container.vector.configuration",
            "network": "sentinel.container.vector.network",
            "resources": "sentinel.container.vector.resources",
            "llm_behavior": "sentinel.container.vector.llm_behavior",
        }

        for key, gauge_name in _vector_key_to_gauge.items():
            score = vector_scores.get(key)
            if score is not None:
                metric_map[gauge_name] = (_clamp(score), attrs)

        self._cache[container_id] = metric_map

        logger.debug(
            "Cached trust metrics for %s (%s): score=%.1f, vectors=%s",
            container_name,
            container_id,
            trust_score,
            vector_scores,
        )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* to the ``[lo, hi]`` range."""
    return max(lo, min(hi, value))
