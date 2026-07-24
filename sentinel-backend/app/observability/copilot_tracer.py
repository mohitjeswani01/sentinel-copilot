"""
Sentinel Copilot Backend — Meta-Observability Tracing.

Instruments the copilot's own decision cycle with OpenTelemetry spans so
the agent's reasoning is visible in SigNoz's Trace Explorer, tagged with
``component=sentinel-copilot-brain`` to distinguish copilot spans from
normal scanner / API spans.

Usage in loop.py::

    with trace_copilot_step("investigate", container_id="abc", trust_score=42.0):
        result = await inv.investigate(...)
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

from opentelemetry import trace
from opentelemetry.trace import StatusCode

logger = logging.getLogger(__name__)

_TRACER_NAME = "sentinel-copilot-brain"
_COMPONENT_ATTR = "component"
_COMPONENT_VALUE = "sentinel-copilot-brain"


def _get_tracer() -> trace.Tracer:
    """Return a named tracer from the global TracerProvider."""
    return trace.get_tracer(_TRACER_NAME)


@contextmanager
def trace_copilot_step(
    step_name: str,
    *,
    attributes: dict[str, Any] | None = None,
) -> Generator[trace.Span, None, None]:
    """Context manager that wraps a copilot step in an OTel span.

    The span is created as a child of whatever span is currently active
    (which for the copilot cycle should be the ``copilot_cycle`` parent).

    Args:
        step_name: Name for the span (e.g. ``"detect"``, ``"investigate"``).
        attributes: Optional extra span attributes (container_id, etc.).

    Yields:
        The active ``Span`` so callers can add events or set status.
    """
    tracer = _get_tracer()
    merged_attrs: dict[str, Any] = {_COMPONENT_ATTR: _COMPONENT_VALUE}
    if attributes:
        merged_attrs.update(attributes)

    with tracer.start_as_current_span(
        step_name,
        attributes=merged_attrs,  # type: ignore[arg-type]
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            raise


@contextmanager
def trace_copilot_cycle(
    container_id: str,
    container_name: str,
    trust_score: float,
    risk_tier: str,
) -> Generator[trace.Span, None, None]:
    """Top-level parent span for one full copilot cycle run.

    All ``trace_copilot_step()`` calls inside this context become
    child spans of the ``copilot_cycle`` span, forming a waterfall
    in SigNoz's Trace Explorer.

    Args:
        container_id: Docker container ID.
        container_name: Human-readable container name.
        trust_score: Numeric trust score 0–100.
        risk_tier: Risk classification string.

    Yields:
        The parent ``Span``.
    """
    tracer = _get_tracer()
    attrs: dict[str, Any] = {
        _COMPONENT_ATTR: _COMPONENT_VALUE,
        "container_id": container_id,
        "container_name": container_name,
        "trust_score": trust_score,
        "risk_tier": risk_tier,
    }

    with tracer.start_as_current_span(
        "copilot_cycle",
        attributes=attrs,  # type: ignore[arg-type]
    ) as span:
        try:
            yield span
        except Exception as exc:
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            raise
