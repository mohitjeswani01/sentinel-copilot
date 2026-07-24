"""
Sentinel Copilot Backend — Shared Pydantic Schemas.

Centralises all response/domain models used across routes, the copilot
investigator, and alert manager so they are importable from a single place.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ── Investigation Models ─────────────────────────────────────────────────────

class TelemetryEvidence(BaseModel):
    """A single piece of supporting telemetry evidence from SigNoz."""

    source: str = Field(..., description="'traces' or 'logs'")
    snippet: str = Field(..., description="Human-readable excerpt from the telemetry")
    raw: dict[str, Any] | None = Field(
        default=None,
        description="Raw response from the MCP tool call for this evidence",
    )


class InvestigationResult(BaseModel):
    """Structured output of ``Investigator.investigate()``."""

    container_id: str
    container_name: str
    trust_score: float
    risk_tier: str

    # Which vector scored lowest and why
    primary_cause: str = Field(
        ...,
        description="Name of the lowest-scoring vector and the reason string from the scorer",
    )
    primary_vector: str = Field(
        ...,
        description="Name of the lowest-scoring vector (identity | configuration | network | resources)",
    )

    # Corroborating telemetry pulled from SigNoz via MCP
    supporting_evidence: list[TelemetryEvidence] = Field(
        default_factory=list,
        description="Real log/trace snippets from SigNoz that corroborate the vector finding",
    )

    # Summary for humans / frontend display
    summary: str = Field(
        ...,
        description="Plain-English paragraph summarising the investigation result",
    )

    # Alert that may have been created
    alert_created: bool = Field(
        default=False,
        description="True if a SigNoz alert was automatically created for this container",
    )
    alert_name: str | None = Field(
        default=None,
        description="The name of the alert rule created in SigNoz (if any)",
    )

    investigated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 timestamp of when the investigation ran",
    )
