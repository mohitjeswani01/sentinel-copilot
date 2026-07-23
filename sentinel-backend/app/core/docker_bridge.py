"""
Sentinel Copilot Backend — Docker Bridge.

Provides a safe abstraction over the Docker Python SDK for host / WSL2
container discovery and management.  All functions handle connection
failures gracefully so the rest of the application can degrade without
crashing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import docker
from docker.errors import DockerException, NotFound

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Module-level client (lazy singleton) ─────────────────────────────────────
_client: docker.DockerClient | None = None


def get_docker_client() -> docker.DockerClient:
    """Return a connected Docker client, creating one on first call.

    The client connects to the socket specified by
    ``settings.DOCKER_HOST``.  If the daemon is unreachable a clear
    ``ConnectionError`` is raised so callers can handle it explicitly.

    Returns:
        docker.DockerClient: A connected Docker client instance.

    Raises:
        ConnectionError: If the Docker daemon is unreachable.
    """
    global _client  # noqa: PLW0603
    if _client is not None:
        return _client

    try:
        _client = docker.DockerClient(base_url=settings.DOCKER_HOST)
        _client.ping()
        logger.info(
            "Docker client connected successfully via %s",
            settings.DOCKER_HOST,
        )
        return _client
    except DockerException as exc:
        _client = None
        raise ConnectionError(
            f"Unable to connect to Docker daemon at {settings.DOCKER_HOST}. "
            f"Ensure Docker is running and the socket is accessible. "
            f"Original error: {exc}"
        ) from exc


def list_running_containers() -> list[dict[str, Any]]:
    """Scan running Docker containers and return lightweight summaries.

    Returns:
        A list of dicts with keys: ``id``, ``name``, ``image``, ``status``,
        ``created``, ``labels``, ``ports``.
    """
    client = get_docker_client()
    containers = client.containers.list(all=False)
    summaries: list[dict[str, Any]] = []

    for c in containers:
        created_raw = c.attrs.get("Created", "")
        try:
            created = (
                datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                if isinstance(created_raw, str) and created_raw
                else None
            )
        except (ValueError, TypeError):
            created = None

        summaries.append(
            {
                "id": c.short_id,
                "name": c.name,
                "image": ",".join(c.image.tags) if c.image and c.image.tags else str(c.image),
                "status": c.status,
                "created": created.isoformat() if created else created_raw,
                "labels": dict(c.labels) if c.labels else {},
                "ports": c.ports or {},
            }
        )

    logger.debug("Discovered %d running container(s)", len(summaries))
    return summaries


def get_container_inspect(container_id: str) -> dict[str, Any]:
    """Return the full Docker inspection JSON for a container.

    Args:
        container_id: The container ID or name.

    Returns:
        Detailed inspection dictionary.

    Raises:
        NotFound: If the container does not exist.
        ConnectionError: If the Docker daemon is unreachable.
    """
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        return container.attrs  # type: ignore[return-value]
    except NotFound:
        logger.warning("Container %s not found", container_id)
        raise
    except DockerException as exc:
        logger.error("Error inspecting container %s: %s", container_id, exc)
        raise


def get_container_stats(
    container_id: str,
    *,
    stream: bool = False,
) -> dict[str, Any]:
    """Fetch CPU / Memory stats for a container.

    Args:
        container_id: The container ID or name.
        stream: If ``True``, returns a generator of stats snapshots.
                Defaults to ``False`` (single snapshot).

    Returns:
        A dictionary with CPU, memory, and I/O statistics.

    Raises:
        NotFound: If the container does not exist.
        ConnectionError: If the Docker daemon is unreachable.
    """
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        return container.stats(stream=stream)  # type: ignore[return-value]
    except NotFound:
        logger.warning("Container %s not found for stats", container_id)
        raise
    except DockerException as exc:
        logger.error("Error fetching stats for %s: %s", container_id, exc)
        raise


def kill_container(container_id: str) -> bool:
    """Stop / kill a container identified as a critical threat.

    Performs a graceful stop (10 s timeout) followed by a forced kill if
    the container does not halt.

    Args:
        container_id: The container ID or name.

    Returns:
        ``True`` if the container was stopped successfully, ``False``
        otherwise.
    """
    client = get_docker_client()
    try:
        container = client.containers.get(container_id)
        logger.warning(
            "Initiating kill on container %s (%s)",
            container.name,
            container.short_id,
        )
        container.stop(timeout=10)
        logger.info(
            "Container %s (%s) stopped successfully",
            container.name,
            container.short_id,
        )
        return True
    except NotFound:
        logger.warning(
            "Container %s already removed before kill could execute",
            container_id,
        )
        return False
    except DockerException as exc:
        logger.error(
            "Failed to kill container %s: %s",
            container_id,
            exc,
        )
        return False
