"""
Sentinel Copilot — Trust Vector: Network.

Evaluates container network exposure by analysing port bindings:
  - Ports bound to ``0.0.0.0`` (publicly reachable) are high risk.
  - Ports bound to ``127.0.0.1`` only are considered safe.
  - Critical / sensitive ports (22-SSH, 23-Telnet, 2375-Docker API)
    carry additional penalties.

Weight in overall Trust Score: **20 %**
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Ports that are especially dangerous to expose publicly.
CRITICAL_PORTS: set[int] = {22, 23, 2375, 2376, 5432, 3306, 6379, 27017}


def score_network(container_inspect: dict[str, Any]) -> tuple[float, str]:
    """Score the network vector for a single container.

    Scoring logic (ported from archestra-sentinel):

    Base score starts at **100**.

    For each port binding entry:
    * Bound to ``0.0.0.0`` (all interfaces):
      - Normal port: **−15** per binding.
      - Critical port (SSH, Telnet, Docker API, etc.): **−25** per binding.
    * Bound to ``127.0.0.1``: no penalty (considered safe / local-only).
    * No port bindings at all: score stays at 100 (no network exposure).

    Final score is clamped to [0, 100].

    Args:
        container_inspect: Full ``docker inspect`` dict for the container.

    Returns:
        A ``(score, reasoning)`` tuple.
    """
    score = 100.0
    reasons: list[str] = []

    host_config = container_inspect.get("HostConfig", {})
    port_bindings = host_config.get("PortBindings") or {}

    if not port_bindings:
        return 100.0, "No port bindings — no network exposure"

    for container_port_proto, bindings in port_bindings.items():
        if not bindings:
            continue

        # Parse port number from "8080/tcp" style key
        try:
            port_num = int(container_port_proto.split("/")[0])
        except (ValueError, IndexError):
            port_num = 0

        is_critical = port_num in CRITICAL_PORTS

        for binding in bindings:
            host_ip = binding.get("HostIp", "")
            host_port = binding.get("HostPort", "")

            if host_ip == "127.0.0.1" or host_ip == "::1":
                reasons.append(
                    f"Port {port_num}→{host_port} bound to {host_ip} (local-only, safe)"
                )
            elif host_ip in ("0.0.0.0", "", "::"):
                # Empty HostIp defaults to 0.0.0.0 in Docker
                if is_critical:
                    score -= 25
                    reasons.append(
                        f"CRITICAL port {port_num}→{host_port} exposed on 0.0.0.0 (−25)"
                    )
                else:
                    score -= 15
                    reasons.append(
                        f"Port {port_num}→{host_port} exposed on 0.0.0.0 (−15)"
                    )
            else:
                # Bound to a specific non-loopback IP — moderate risk
                score -= 10
                reasons.append(
                    f"Port {port_num}→{host_port} bound to {host_ip} (−10)"
                )

    score = max(0.0, min(100.0, score))

    reasoning = "; ".join(reasons) if reasons else "No significant network findings"
    logger.debug("Network score=%.1f: %s", score, reasoning)

    return score, reasoning
