"""
Legacy VideoSDK adapter for the shared Swiggy MCP client.

The hosted LemonSlice merge uses `swiggy_mcp_client.py` directly. This module
keeps the legacy VideoSDK entrypoints working when the `videosdk` package is
installed in that environment.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from functools import partial
from typing import Any

from swiggy_mcp_client import (
    SWIGGY_MCP_ENDPOINTS,
    SwiggyMCPClient,
    create_oauth_provider,
    sanitize_schema,
    test_login,
)

logger = logging.getLogger(__name__)

try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from videosdk.agents.mcp.mcp_server import MCPServiceProvider
    from videosdk.agents.utils import ToolError, create_generic_mcp_adapter

    _VIDEOSDK_AVAILABLE = True
except ImportError:  # pragma: no cover - legacy runtime only
    ClientSession = Any  # type: ignore[assignment]
    MCPServiceProvider = object  # type: ignore[assignment]
    ToolError = RuntimeError  # type: ignore[assignment]
    create_generic_mcp_adapter = None  # type: ignore[assignment]
    streamablehttp_client = None  # type: ignore[assignment]
    _VIDEOSDK_AVAILABLE = False


async def _route_tool_call(client: SwiggyMCPClient, tool_name: str, parameters: dict[str, Any]):
    """Adapt the shared client result shape to the legacy VideoSDK tool API."""
    try:
        result = await client.call_tool(tool_name, parameters)
        return result["result"]
    except Exception as exc:
        raise ToolError(f"Tool execution failed for '{tool_name}': {exc}") from exc


if _VIDEOSDK_AVAILABLE:  # pragma: no branch - defined only for the legacy runtime

    class SwiggyMCPServer(MCPServiceProvider):
        """Unified MCP provider for all Swiggy services (Food, Instamart, Dineout)."""

        def __init__(self):
            """Initialize the legacy MCP provider around the shared Swiggy client."""
            super().__init__(connection_timeout=300.0)
            self.auth = create_oauth_provider()
            self.client = SwiggyMCPClient()
            self._extra_sessions: dict[str, ClientSession] = {}
            self._extra_stacks: list[AsyncExitStack] = []

        def get_stream_provider(self):
            """Return the primary stream provider required by the VideoSDK base class."""
            return streamablehttp_client(
                url=SWIGGY_MCP_ENDPOINTS["swiggy-food"],
                auth=self.auth,
            )

        async def connect(self):
            """Connect the VideoSDK provider and the underlying shared client."""
            await super().connect()
            await self.client.connect()
            logger.info("Connected shared Swiggy MCP client for legacy VideoSDK runtime")

        async def get_available_tools(self):
            """Translate the shared tool catalog into VideoSDK framework tools."""
            if not self.is_ready:
                raise RuntimeError("Not connected")

            if self.tool_registry.has_valid_cache():
                return self.tool_registry.get_cached_tools()

            framework_tools = []
            for tool in await self.client.list_tools():
                executor = partial(_route_tool_call, self.client, tool.name)
                adapted = create_generic_mcp_adapter(
                    tool_name=tool.name,
                    tool_description=tool.description,
                    input_schema=sanitize_schema(tool.input_schema),
                    client_call_function=executor,
                )
                framework_tools.append(adapted)

            self.tool_registry.update_cache(framework_tools)
            logger.info(
                "Registered %s unique Swiggy tools across %s services",
                len(framework_tools),
                len(SWIGGY_MCP_ENDPOINTS),
            )
            return framework_tools

        async def disconnect(self):
            """Disconnect the shared client before releasing the base provider."""
            await self.client.disconnect()
            await super().disconnect()

        def __repr__(self):
            """Return a readable identifier for logs and debugging."""
            return f"SwiggyMCPServer(services={list(SWIGGY_MCP_ENDPOINTS.keys())})"


def build_swiggy_mcp_servers() -> list["SwiggyMCPServer"]:
    """Build a single unified MCP server for all Swiggy services."""

    if not _VIDEOSDK_AVAILABLE:
        raise RuntimeError(
            "The legacy Swiggy VideoSDK runtime requires the 'videosdk-agents' package. "
            "Use swiggy_mcp_client.py from the hosted backend instead."
        )

    server = SwiggyMCPServer()
    logger.info("Configured unified Swiggy MCP: %s", list(SWIGGY_MCP_ENDPOINTS.keys()))
    return [server]


if __name__ == "__main__":
    """Run the one-time Swiggy OAuth login flow when executed directly."""
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_login())
