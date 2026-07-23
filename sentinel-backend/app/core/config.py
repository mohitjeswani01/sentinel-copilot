"""
Sentinel Copilot Backend — Central Configuration.

All application settings are loaded from environment variables (or a `.env`
file at the project root) using Pydantic Settings.  Import the global
``settings`` singleton from this module wherever configuration values are
needed.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration backed by environment variables.

    Pydantic Settings reads values in the following priority order:
    1. Explicit environment variables.
    2. Entries in the ``.env`` file (if present).
    3. Defaults declared below.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── General ──────────────────────────────────────────────────────────
    PROJECT_NAME: str = "Sentinel Copilot Backend"
    ENVIRONMENT: str = "development"

    # ── SigNoz / OpenTelemetry ───────────────────────────────────────────
    SIGNOZ_OTLP_ENDPOINT: str = "http://localhost:4317"
    """OTLP gRPC endpoint for traces & metrics ingestion."""

    SIGNOZ_MCP_URL: str = "http://localhost:8000/mcp"
    """SigNoz MCP HTTP JSON-RPC endpoint."""

    SIGNOZ_API_KEY: str = ""
    """Optional API key for authenticated SigNoz deployments."""

    # ── Docker ───────────────────────────────────────────────────────────
    DOCKER_HOST: str = "unix:///var/run/docker.sock"
    """Path to the Docker daemon socket."""

    # ── Scanner ──────────────────────────────────────────────────────────
    SCAN_INTERVAL_SECONDS: int = 10
    """Interval (seconds) between background container scan cycles."""


# ── Global singleton ─────────────────────────────────────────────────────────
settings = Settings()
