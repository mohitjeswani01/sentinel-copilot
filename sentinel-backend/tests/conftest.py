"""Shared pytest fixtures for the Sentinel Copilot backend test suite.

Nothing here touches Docker, SigNoz, or the network.  The trust vectors are
pure functions over ``docker inspect`` / ``docker stats`` dicts, so they are
tested against hand-built fixtures that mirror the real Docker API shape.  The
API layer reads only from the scanner's in-memory store, which is seeded
directly.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.models import schemas
from app.scanner import background_scanner


# ─────────────────────────────────────────────────────────────────────────────
# Docker inspect / stats builders
#
# Key names and nesting match a real `docker inspect` / `docker stats` payload.
# Defaults describe a well-behaved container (sanctioned image, non-root, no
# privileged flag, both resource limits set, no published ports) so each test
# overrides only the one thing it is about.
# ─────────────────────────────────────────────────────────────────────────────

def make_inspect(
    *,
    image: str | None = "nginx:1.25",
    image_digest: str = "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    user: str = "appuser",
    privileged: bool = False,
    readonly_rootfs: bool = False,
    memory: int = 512 * 1024 * 1024,
    nano_cpus: int = 1_000_000_000,
    cpu_quota: int = 0,
    port_bindings: dict[str, list[dict[str, str]] | None] | None = None,
) -> dict[str, Any]:
    """Build a minimal but realistically-shaped ``docker inspect`` dict.

    Args:
        image: Value for ``Config.Image``.  Pass ``None`` to omit it entirely,
            which forces the identity vector onto its ``Image`` digest fallback.
        image_digest: Value for the top-level ``Image`` field.
        port_bindings: ``HostConfig.PortBindings``, e.g.
            ``{"22/tcp": [{"HostIp": "0.0.0.0", "HostPort": "2222"}]}``.
    """
    config: dict[str, Any] = {"User": user}
    if image is not None:
        config["Image"] = image

    return {
        "Id": "c0ffee1234567890",
        "Name": "/test-container",
        "Image": image_digest,
        "Config": config,
        "HostConfig": {
            "Privileged": privileged,
            "ReadonlyRootfs": readonly_rootfs,
            "Memory": memory,
            "NanoCpus": nano_cpus,
            "CpuQuota": cpu_quota,
            "CpuPeriod": 100_000 if cpu_quota else 0,
            "PortBindings": port_bindings,
        },
    }


def make_stats(
    *,
    cpu_percent: float | None = None,
    mem_percent: float | None = None,
    mem_limit: int = 1_000_000_000,
    online_cpus: int = 1,
) -> dict[str, Any]:
    """Build a ``docker stats`` snapshot that yields the requested percentages.

    The resources vector derives CPU% from the delta between ``cpu_stats`` and
    ``precpu_stats``, so the deltas are solved backwards from *cpu_percent*.

    Passing ``None`` for either percentage omits that section, which is what the
    real API looks like for a container whose stats could not be collected —
    the vector must report "unavailable" rather than assume a value.
    """
    stats: dict[str, Any] = {}

    if cpu_percent is not None:
        system_delta = 1_000_000_000
        cpu_delta = int((cpu_percent / 100.0) * system_delta / online_cpus)
        stats["precpu_stats"] = {
            "cpu_usage": {"total_usage": 0},
            "system_cpu_usage": 0,
        }
        stats["cpu_stats"] = {
            "cpu_usage": {"total_usage": cpu_delta},
            "system_cpu_usage": system_delta,
            "online_cpus": online_cpus,
        }

    if mem_percent is not None:
        stats["memory_stats"] = {
            "usage": int((mem_percent / 100.0) * mem_limit),
            "limit": mem_limit,
        }

    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Scan-store helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_scan_result(
    container_id: str,
    container_name: str,
    trust_score: float,
    risk_tier: str,
    vector_scores: dict[str, float] | None = None,
    vector_reasons: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a scan-store entry in the exact shape ``_score_container`` returns."""
    return {
        "container_id": container_id,
        "container_name": container_name,
        "trust_score": trust_score,
        "risk_tier": risk_tier,
        "vector_scores": vector_scores
        or {
            "identity": 100.0,
            "configuration": 100.0,
            "network": 100.0,
            "resources": 100.0,
            "llm_behavior": 100.0,
        },
        "vector_reasons": vector_reasons
        or {
            "identity": "Image 'nginx' matches sanctioned whitelist",
            "configuration": "Non-root user 'appuser' (+0, baseline)",
            "network": "No port bindings — no network exposure",
            "resources": "Memory limit set to 512MB (+0)",
            "llm_behavior": "No LLM activity detected — not applicable",
        },
    }


@pytest.fixture(autouse=True)
def clean_state() -> Any:
    """Reset both module-level in-memory stores around every test.

    The scan store and the audit log are process-global by design (see
    ``ARCHITECTURE.md`` → "No persistence"), so without this the tests would
    leak state into each other and pass or fail depending on ordering.
    """
    background_scanner._last_scan_results.clear()
    schemas._audit_log.clear()
    yield
    background_scanner._last_scan_results.clear()
    schemas._audit_log.clear()


@pytest.fixture
def scan_store() -> dict[str, dict[str, Any]]:
    """The scanner's in-memory store, writable by tests.

    The route handlers call ``get_scan_results()`` / ``get_container_result()``,
    which read this module global — so seeding it here is enough to drive the
    whole API layer without Docker.
    """
    return background_scanner._last_scan_results


@pytest.fixture
def client() -> TestClient:
    """A ``TestClient`` over just the API router.

    Deliberately *not* ``app.main:app``: that app's lifespan starts the
    background scanner and the OTLP exporters.  Mounting the router on a bare
    FastAPI instance exercises the real routes, real Pydantic response models,
    and real status codes with no side effects.
    """
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)
