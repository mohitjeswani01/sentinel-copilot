"""
Sentinel Copilot — Trust Vector: Identity.

Evaluates a container's identity by checking its image name against a
curated whitelist of sanctioned images.  Unknown / unsanctioned images
receive a severe trust penalty.

Weight in overall Trust Score: **30 %**
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Sanctioned Images Whitelist ──────────────────────────────────────────────
# Glob-style patterns.  Extend this list as new trusted images are approved.
# Images matching any pattern are considered *sanctioned*.
SANCTIONED_IMAGES: list[str] = [
    "signoz/*",
    "signoz-*",
    "clickhouse/*",
    "docker.io/signoz/*",
    "goog.io/signoz/*",
    "otel/*",
    "opentelemetry/*",
    "postgres",
    "postgres:*",
    "redis",
    "redis:*",
    "nginx",
    "nginx:*",
    "python",
    "python:*",
    "node",
    "node:*",
    "ubuntu",
    "ubuntu:*",
    "alpine",
    "alpine:*",
]


def _image_name_from_inspect(container_inspect: dict[str, Any]) -> str:
    """Extract the image name from a Docker inspect dict.

    Tries ``Config.Image`` first (the user-specified tag), then falls back
    to the ``Image`` field (usually a sha256 digest).
    """
    config = container_inspect.get("Config", {})
    image = config.get("Image", "")
    if not image:
        image = container_inspect.get("Image", "")
    return image.lower()


def _is_sanctioned(image: str) -> bool:
    """Return ``True`` if *image* matches any sanctioned pattern."""
    for pattern in SANCTIONED_IMAGES:
        if fnmatch.fnmatch(image, pattern.lower()):
            return True
        # Also check without registry prefix (e.g. "docker.io/library/nginx")
        short = image.split("/")[-1] if "/" in image else image
        if fnmatch.fnmatch(short, pattern.lower()):
            return True
    return False


def score_identity(container_inspect: dict[str, Any]) -> tuple[float, str]:
    """Score the identity vector for a single container.

    Scoring logic (ported from archestra-sentinel):
    * Image matches sanctioned whitelist → **100** (fully trusted).
    * Image is unrecognised (not in whitelist) → **20** (unsanctioned,
      high risk — unknown provenance).

    Args:
        container_inspect: Full ``docker inspect`` dict for the container.

    Returns:
        A ``(score, reasoning)`` tuple where *score* is 0–100 and
        *reasoning* is a human-readable explanation.
    """
    image = _image_name_from_inspect(container_inspect)

    if not image or image.startswith("sha256:"):
        return 10.0, f"Image has no tag (digest only: {image[:20]}…) — unverifiable identity"

    if _is_sanctioned(image):
        return 100.0, f"Image '{image}' matches sanctioned whitelist"

    return 20.0, f"Image '{image}' is NOT in the sanctioned whitelist — unsanctioned identity"
