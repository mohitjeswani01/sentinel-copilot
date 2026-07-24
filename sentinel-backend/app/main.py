"""
Sentinel Copilot Backend — FastAPI Application Entry Point.

Wires together:
  * OpenTelemetry SDK initialization (traces + metrics → SigNoz).
  * Background container scanner (trust engine + metric emission).
  * CORS middleware for frontend communication.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.observability.otel_setup import setup_opentelemetry
from app.scanner.background_scanner import start_scanner
from app.api.routes import router as api_router

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler — runs on startup / shutdown."""
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("Starting %s …", settings.PROJECT_NAME)

    setup_opentelemetry()
    logger.info("OpenTelemetry initialised → %s", settings.SIGNOZ_OTLP_ENDPOINT)

    start_scanner()
    logger.info("Background scanner started (interval=%ds)", settings.SCAN_INTERVAL_SECONDS)

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("Shutting down %s …", settings.PROJECT_NAME)


# ── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS (allow frontend on any local port during development) ───────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ───────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")


# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/healthz", tags=["system"])
async def healthz() -> dict[str, str]:
    """Basic liveness probe."""
    return {"status": "ok", "service": settings.PROJECT_NAME}
