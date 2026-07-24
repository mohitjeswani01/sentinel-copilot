"""
Sentinel Copilot Backend — SigNoz MCP Client.

Provides a typed wrapper around SigNoz's MCP (Model Context Protocol)
server, which exposes observability tools (traces, logs, metrics queries)
via JSON-RPC 2.0 over HTTP.

MCP Server endpoint: ``settings.SIGNOZ_MCP_URL`` (default: ``http://localhost:8000/mcp``)
Health check: ``/livez`` (NOT ``/health``)

Protocol reference:
  - MCP uses JSON-RPC 2.0 with methods like ``initialize``, ``tools/list``,
    ``tools/call``.
  - Each request has ``jsonrpc: "2.0"``, ``id``, ``method``, and ``params``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class MCPClientError(Exception):
    """Raised when the MCP server is unreachable or returns an error."""


class MCPToolCallError(MCPClientError):
    """Raised when a specific tool call fails."""


class SentinelMCPClient:
    """Async client for the SigNoz MCP server.

    Usage::

        async with SentinelMCPClient() as mcp:
            tools = await mcp.list_available_tools()
            result = await mcp.call_tool("search_traces", {"service_name": "..."})
    """

    def __init__(
        self,
        mcp_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._mcp_url = mcp_url or settings.SIGNOZ_MCP_URL
        self._api_key = api_key if api_key is not None else settings.SIGNOZ_API_KEY
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._request_id = 0
        self._initialized = False

        if not self._api_key:
            raise MCPClientError(
                "SIGNOZ_API_KEY is empty or not configured. MCP authentication requires a valid API key."
            )

    async def __aenter__(self) -> SentinelMCPClient:
        headers = {
            "SIGNOZ-API-KEY": self._api_key,
            "Authorization": f"Bearer {self._api_key}",
        }
        self._client = httpx.AsyncClient(timeout=self._timeout, headers=headers)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _next_id(self) -> int:
        """Generate a sequential JSON-RPC request ID."""
        self._request_id += 1
        return self._request_id

    async def _send_jsonrpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a JSON-RPC 2.0 request to the MCP server.

        Args:
            method: The JSON-RPC method name (e.g. ``initialize``, ``tools/list``).
            params: Optional parameters dict.

        Returns:
            The ``result`` field from the JSON-RPC response.

        Raises:
            MCPClientError: If the server is unreachable or returns a
                malformed response.
            MCPToolCallError: If the JSON-RPC response contains an
                ``error`` field.
        """
        if self._client is None:
            raise MCPClientError(
                "Client not initialized — use 'async with SentinelMCPClient() as mcp:'"
            )

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        logger.debug("MCP → %s %s", method, params or "")

        try:
            response = await self._client.post(
                self._mcp_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise MCPClientError(
                f"MCP server unreachable at {self._mcp_url}: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise MCPClientError(
                f"MCP server returned HTTP {exc.response.status_code}: "
                f"{exc.response.text[:200]}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise MCPClientError(
                f"MCP request timed out after {self._timeout}s: {exc}"
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise MCPClientError(
                f"MCP server returned non-JSON response: {response.text[:200]}"
            ) from exc

        # Check for JSON-RPC error
        if "error" in body:
            err = body["error"]
            code = err.get("code", "?")
            msg = err.get("message", str(err))
            raise MCPToolCallError(
                f"MCP JSON-RPC error (code={code}): {msg}"
            )

        logger.debug("MCP ← %s result keys: %s", method, list(body.get("result", {}).keys()) if isinstance(body.get("result"), dict) else type(body.get("result")))

        return body.get("result", body)

    # ── MCP Protocol Methods ─────────────────────────────────────────────

    async def initialize(self) -> dict[str, Any]:
        """Send the MCP ``initialize`` handshake.

        Returns:
            Server capabilities and metadata.
        """
        result = await self._send_jsonrpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "sentinel-copilot",
                    "version": "0.1.0",
                },
            },
        )
        self._initialized = True
        logger.info("MCP initialized: %s", result)
        return result

    async def send_initialized_notification(self) -> None:
        """Send the ``notifications/initialized`` notification after handshake.

        This is required by MCP protocol after a successful ``initialize``.
        Notifications have no ``id`` field and expect no response.
        """
        if self._client is None:
            raise MCPClientError("Client not initialized")

        payload = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        try:
            await self._client.post(
                self._mcp_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            logger.debug("MCP notifications/initialized sent")
        except Exception as exc:
            logger.warning("Failed to send initialized notification: %s", exc)

    async def list_available_tools(self) -> list[dict[str, Any]]:
        """Discover available tools on the MCP server via ``tools/list``.

        Returns:
            A list of tool descriptors, each with ``name``, ``description``,
            and ``inputSchema``.
        """
        result = await self._send_jsonrpc("tools/list")

        # The tools/list response has {"tools": [...]}
        if isinstance(result, dict):
            tools = result.get("tools", [])
        elif isinstance(result, list):
            tools = result
        else:
            tools = []

        logger.info(
            "MCP tools/list: %d tool(s) discovered — %s",
            len(tools),
            [t.get("name", "?") for t in tools],
        )
        return tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a specific tool on the MCP server via ``tools/call``.

        Args:
            tool_name: The tool name as returned by ``tools/list``.
            arguments: Tool-specific arguments matching the tool's input schema.

        Returns:
            The tool's response data.

        Raises:
            MCPToolCallError: If the tool call fails.
        """
        result = await self._send_jsonrpc(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments or {},
            },
        )
        logger.info("MCP tools/call '%s' returned: %s", tool_name, type(result))
        return result

    # ── Convenience Wrappers ─────────────────────────────────────────────
    # Typed wrappers for real tools discovered from SigNoz's MCP server.

    async def query_services(
        self,
        time_range: str = "6h",
        limit: int = 50,
    ) -> dict[str, Any]:
        """List APM services known to SigNoz via ``signoz_list_services``."""
        args: dict[str, Any] = {
            "timeRange": time_range,
            "limit": limit,
        }
        return await self.call_tool("signoz_list_services", args)

    async def search_traces(
        self,
        service_name: str = "",
        limit: int = 10,
        time_range: str = "1h",
    ) -> dict[str, Any]:
        """Search raw trace span rows in SigNoz via ``signoz_search_traces``."""
        args: dict[str, Any] = {
            "limit": limit,
            "timeRange": time_range,
        }
        if service_name:
            args["service"] = service_name
        return await self.call_tool("signoz_search_traces", args)

    async def search_logs(
        self,
        service_name: str = "",
        limit: int = 10,
        search_text: str = "",
        time_range: str = "1h",
    ) -> dict[str, Any]:
        """Search log records in SigNoz via ``signoz_search_logs``."""
        args: dict[str, Any] = {
            "limit": limit,
            "timeRange": time_range,
        }
        if service_name:
            args["service"] = service_name
        if search_text:
            args["searchText"] = search_text
        return await self.call_tool("signoz_search_logs", args)

    async def get_metrics(
        self,
        metric_name: str,
        time_range: str = "1h",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Query metric values and breakdowns from SigNoz via ``signoz_query_metrics``."""
        args: dict[str, Any] = {
            "metricName": metric_name,
            "timeRange": time_range,
            **kwargs,
        }
        return await self.call_tool("signoz_query_metrics", args)


# ── Module-level helper ──────────────────────────────────────────────────────

async def discover_mcp_tools() -> list[dict[str, Any]]:
    """Perform the full MCP discovery handshake and return available tools.

    This is the MANDATORY first step per the task spec — call ``initialize``,
    then ``tools/list``, and log the raw response.

    Returns:
        List of tool descriptors from the MCP server.

    Raises:
        MCPClientError: If the MCP server is unreachable.
    """
    async with SentinelMCPClient() as mcp:
        logger.info("═══ MCP Discovery: Connecting to %s ═══", settings.SIGNOZ_MCP_URL)

        # Step 1: Initialize handshake
        init_result = await mcp.initialize()
        logger.info("MCP initialize response:\n%s", init_result)

        # Step 1.5: Send initialized notification
        await mcp.send_initialized_notification()

        # Step 2: Discover available tools
        tools = await mcp.list_available_tools()
        logger.info(
            "═══ MCP Discovery Complete: %d tools ═══\n%s",
            len(tools),
            "\n".join(
                f"  • {t.get('name', '?')}: {t.get('description', 'no description')}"
                for t in tools
            ) if tools else "  (no tools found)",
        )

        return tools
