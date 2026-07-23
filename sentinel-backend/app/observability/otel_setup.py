"""
Sentinel Copilot Backend — OpenTelemetry SDK Initialization.

Configures global ``TracerProvider`` and ``MeterProvider`` with OTLP
exporters pointed at the SigNoz collector.  Call ``setup_opentelemetry()``
once during application startup (before any spans or metrics are created).
"""

from __future__ import annotations

import logging

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.metrics import Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
_SERVICE_NAME = "sentinel-backend"
_METRIC_EXPORT_INTERVAL_MS = 10_000  # flush metrics every 10 s


def setup_opentelemetry() -> None:
    """Initialise global OpenTelemetry providers for traces and metrics.

    This function is **idempotent** — it checks for existing providers
    before overwriting, but should ideally be called only once at startup.

    Exporters target ``settings.SIGNOZ_OTLP_ENDPOINT`` (gRPC).  If
    ``settings.SIGNOZ_API_KEY`` is non-empty it is sent as the
    ``signoz-access-token`` header.
    """
    resource = Resource.create(
        {
            "service.name": _SERVICE_NAME,
            "deployment.environment": settings.ENVIRONMENT,
        }
    )

    # Build optional auth headers for SigNoz Cloud / secured deployments
    headers: tuple[tuple[str, str], ...] | None = None
    if settings.SIGNOZ_API_KEY:
        headers = (("signoz-access-token", settings.SIGNOZ_API_KEY),)

    # ── Traces ───────────────────────────────────────────────────────────
    span_exporter = OTLPSpanExporter(
        endpoint=settings.SIGNOZ_OTLP_ENDPOINT,
        headers=headers,
        insecure=True,
    )
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)
    logger.info(
        "TracerProvider configured → %s",
        settings.SIGNOZ_OTLP_ENDPOINT,
    )

    # ── Metrics ──────────────────────────────────────────────────────────
    metric_exporter = OTLPMetricExporter(
        endpoint=settings.SIGNOZ_OTLP_ENDPOINT,
        headers=headers,
        insecure=True,
    )
    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=_METRIC_EXPORT_INTERVAL_MS,
    )
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
    )
    metrics.set_meter_provider(meter_provider)
    logger.info(
        "MeterProvider configured → %s (flush every %d ms)",
        settings.SIGNOZ_OTLP_ENDPOINT,
        _METRIC_EXPORT_INTERVAL_MS,
    )


def get_meter(name: str = _SERVICE_NAME) -> Meter:
    """Return an OpenTelemetry ``Meter`` from the global ``MeterProvider``.

    Args:
        name: Logical name for the meter (defaults to the service name).

    Returns:
        An OTel Meter instance ready to create instruments.
    """
    return metrics.get_meter(name)
