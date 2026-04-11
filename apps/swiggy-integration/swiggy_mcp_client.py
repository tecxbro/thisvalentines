"""
Runtime-agnostic Swiggy MCP client.

This module owns the shared OAuth flow, token storage, multi-endpoint connection
management, tool discovery, and direct tool execution. It can be reused by the
legacy VideoSDK runtime as well as the hosted LemonSlice sidecar backend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import webbrowser
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

logger = logging.getLogger(__name__)

TOKEN_FILE = Path(__file__).parent / ".swiggy_tokens.json"
CALLBACK_PORT = 8765
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"

SWIGGY_MCP_ENDPOINTS = {
    "swiggy-food": "https://mcp.swiggy.com/food",
    "swiggy-instamart": "https://mcp.swiggy.com/im",
    "swiggy-dineout": "https://mcp.swiggy.com/dineout",
}


class FileTokenStorage(TokenStorage):
    """Stores OAuth tokens and client info in a local JSON file."""

    def __init__(self, path: Path = TOKEN_FILE):
        """Load any previously saved Swiggy OAuth state from disk."""
        self._path = path
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        """Read the persisted token file if it exists and is valid JSON."""
        if self._path.exists():
            try:
                return json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self) -> None:
        """Persist the current in-memory token payload to disk."""
        self._path.write_text(json.dumps(self._data, indent=2, default=str))

    async def get_tokens(self) -> OAuthToken | None:
        """Return the cached OAuth token set, if one has been saved before."""
        raw = self._data.get("tokens")
        if raw:
            return OAuthToken(**raw)
        return None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        """Store refreshed Swiggy OAuth tokens after login or token rotation."""
        self._data["tokens"] = tokens.model_dump()
        self._save()
        logger.info("Saved Swiggy OAuth tokens to %s", self._path)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        """Return the cached OAuth client registration metadata."""
        raw = self._data.get("client_info")
        if raw:
            return OAuthClientInformationFull(**raw)
        return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        """Persist the dynamic client registration returned by the OAuth server."""
        self._data["client_info"] = client_info.model_dump()
        self._save()
        logger.info("Saved Swiggy OAuth client info")


_auth_result = {"code": None, "state": None, "event": threading.Event()}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        """Capture the authorization code from the local OAuth callback."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]

        if code:
            _auth_result["code"] = code
            _auth_result["state"] = state
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"""
                <html><body style="font-family:sans-serif;text-align:center;padding:60px">
                <h2>Swiggy Login Successful!</h2>
                <p>You can close this tab and go back to the terminal.</p>
                </body></html>
                """
            )
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"<html><body><h2>Login Failed: {error}</h2></body></html>".encode()
            )

        _auth_result["event"].set()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003 - stdlib API
        """Silence the local callback server's default request logging."""
        return


async def _redirect_handler(auth_url: str) -> None:
    """Open the Swiggy OAuth URL in the user's browser."""
    logger.info("Opening browser for Swiggy login")
    print("\nOpening browser for Swiggy login...")
    print(f"If it doesn't open automatically, go to:\n{auth_url}\n")
    webbrowser.open(auth_url)


async def _callback_handler() -> tuple[str, str | None]:
    """Run a temporary localhost server and wait for the OAuth callback."""
    _auth_result["code"] = None
    _auth_result["state"] = None
    _auth_result["event"].clear()

    server = HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    logger.info("Waiting for Swiggy OAuth callback on localhost:%s", CALLBACK_PORT)
    print(f"Waiting for login callback on localhost:{CALLBACK_PORT}...")

    # The OAuth SDK expects an async callback, but the local HTTP server blocks
    # on a threading.Event, so the wait is pushed off the event loop.
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _auth_result["event"].wait)
    server.shutdown()

    code = _auth_result["code"]
    state = _auth_result["state"]
    if not code:
        raise RuntimeError("OAuth callback did not receive an authorization code")

    logger.info("Received Swiggy OAuth callback successfully")
    return code, state


def create_oauth_provider(server_url: str = "https://mcp.swiggy.com") -> OAuthClientProvider:
    """Create the shared OAuth client provider used by every runtime shape."""
    storage = FileTokenStorage()

    client_metadata = OAuthClientMetadata(
        redirect_uris=[REDIRECT_URI],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        client_name="Swiggy Voice Agent",
        scope="mcp:tools mcp:resources mcp:prompts",
    )

    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=client_metadata,
        storage=storage,
        redirect_handler=_redirect_handler,
        callback_handler=_callback_handler,
        timeout=120.0,
    )


def sanitize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize tool schemas so they are safe to pass back into LLM prompts."""

    if not isinstance(schema, dict):
        return schema

    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        if isinstance(value, dict):
            cleaned[key] = sanitize_schema(value)
        elif isinstance(value, list) and key == "type":
            cleaned[key] = value[0] if len(value) == 1 else "string"
        elif isinstance(value, list) and key == "enum":
            cleaned[key] = [str(item) for item in value]
        else:
            cleaned[key] = value

    if "properties" in cleaned and isinstance(cleaned["properties"], dict):
        for prop_name, prop_value in cleaned["properties"].items():
            cleaned["properties"][prop_name] = sanitize_schema(prop_value)

    return cleaned


def to_jsonable(value: Any) -> Any:
    """Convert MCP SDK objects into plain JSON-safe Python structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        try:
            return to_jsonable(value.model_dump())
        except TypeError:
            pass
    if hasattr(value, "__dict__"):
        return to_jsonable(vars(value))
    return str(value)


def extract_tool_text(result: Any, char_limit: int = 4000) -> str:
    """Extract a prompt-friendly text view from an MCP tool result."""
    payload = to_jsonable(result)

    if isinstance(payload, dict):
        content = payload.get("content")
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
            if text_parts:
                return "\n".join(text_parts)[:char_limit]

    text = json.dumps(payload, ensure_ascii=True, indent=2)
    return text[:char_limit]


@dataclass(frozen=True)
class SwiggyToolSpec:
    """Normalized description of a single Swiggy MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    service: str


class SwiggyMCPClient:
    """Shared MCP client for Food, Instamart, and Dineout."""

    def __init__(self) -> None:
        """Initialize the shared OAuth provider and empty MCP session state."""
        self.auth = create_oauth_provider()
        self._primary_stack: AsyncExitStack | None = None
        self._primary_session: ClientSession | None = None
        self._extra_stacks: list[AsyncExitStack] = []
        self._extra_sessions: dict[str, ClientSession] = {}
        self._tool_cache: dict[str, SwiggyToolSpec] = {}
        self._tool_service_map: dict[str, str] = {}
        self._connect_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Return whether the primary MCP session has already been initialized."""
        return self._primary_session is not None

    async def connect(self) -> None:
        """Connect to the primary and secondary Swiggy MCP service endpoints."""
        async with self._connect_lock:
            if self._primary_session is not None:
                return

            # Food is treated as the primary session and the other service
            # endpoints are attached alongside it for tool discovery/routing.
            primary_stack = AsyncExitStack()
            streams = await primary_stack.enter_async_context(
                streamablehttp_client(
                    url=SWIGGY_MCP_ENDPOINTS["swiggy-food"],
                    timeout=timedelta(seconds=30),
                    sse_read_timeout=timedelta(seconds=300),
                    auth=self.auth,
                )
            )
            primary_session = await primary_stack.enter_async_context(
                ClientSession(
                    streams[0],
                    streams[1],
                    read_timeout_seconds=timedelta(seconds=300),
                )
            )
            await primary_session.initialize()

            self._primary_stack = primary_stack
            self._primary_session = primary_session
            logger.info("Connected to swiggy-food (primary)")

            for service_name, url in SWIGGY_MCP_ENDPOINTS.items():
                if service_name == "swiggy-food":
                    continue

                stack = AsyncExitStack()
                streams = await stack.enter_async_context(
                    streamablehttp_client(
                        url=url,
                        timeout=timedelta(seconds=30),
                        sse_read_timeout=timedelta(seconds=300),
                        auth=self.auth,
                    )
                )
                session = await stack.enter_async_context(
                    ClientSession(
                        streams[0],
                        streams[1],
                        read_timeout_seconds=timedelta(seconds=300),
                    )
                )
                await session.initialize()
                self._extra_stacks.append(stack)
                self._extra_sessions[service_name] = session
                logger.info("Connected to %s (%s)", service_name, url)

    async def ensure_connected(self) -> None:
        """Connect lazily when a caller asks for tools or tool execution."""
        if not self.is_connected:
            await self.connect()

    async def disconnect(self) -> None:
        """Close all MCP sessions and clear the cached tool catalog."""
        async with self._connect_lock:
            for stack in reversed(self._extra_stacks):
                try:
                    await stack.aclose()
                except Exception as exc:  # pragma: no cover - defensive cleanup
                    logger.warning("Error closing extra Swiggy session: %s", exc)

            self._extra_stacks.clear()
            self._extra_sessions.clear()
            self._tool_cache.clear()
            self._tool_service_map.clear()

            if self._primary_stack is not None:
                try:
                    await self._primary_stack.aclose()
                except Exception as exc:  # pragma: no cover - defensive cleanup
                    logger.warning("Error closing primary Swiggy session: %s", exc)

            self._primary_stack = None
            self._primary_session = None

    def _all_sessions(self) -> dict[str, ClientSession]:
        """Return the currently open MCP sessions keyed by service name."""
        if self._primary_session is None:
            raise RuntimeError("Swiggy MCP client is not connected")

        sessions = {"swiggy-food": self._primary_session}
        sessions.update(self._extra_sessions)
        return sessions

    async def list_tools(self, refresh: bool = False) -> list[SwiggyToolSpec]:
        """Return the deduplicated Swiggy tool catalog across all services."""
        await self.ensure_connected()

        if self._tool_cache and not refresh:
            return list(self._tool_cache.values())

        seen_names: set[str] = set()
        tool_cache: dict[str, SwiggyToolSpec] = {}
        tool_service_map: dict[str, str] = {}

        for service_name, session in self._all_sessions().items():
            tools = await session.list_tools()
            for tool in tools.tools:
                # Some tool names are shared across services; the cache keeps the
                # first discovered definition and records which service owns it.
                if tool.name in seen_names:
                    continue

                seen_names.add(tool.name)
                tool_cache[tool.name] = SwiggyToolSpec(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=sanitize_schema(tool.inputSchema or {}),
                    service=service_name,
                )
                tool_service_map[tool.name] = service_name

        self._tool_cache = tool_cache
        self._tool_service_map = tool_service_map
        return list(tool_cache.values())

    async def call_tool(
        self, tool_name: str, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Route a tool call to the owning service and normalize the result."""
        await self.ensure_connected()
        await self.list_tools()

        service_name = self._tool_service_map.get(tool_name)
        if service_name is None:
            await self.list_tools(refresh=True)
            service_name = self._tool_service_map.get(tool_name)
        if service_name is None:
            raise ValueError(f"Unknown Swiggy tool: {tool_name}")

        # The cached service map lets callers treat the Swiggy tool space as a
        # single catalog even though the tools live behind multiple endpoints.
        session = self._all_sessions()[service_name]
        raw_result = await session.call_tool(tool_name, parameters or {})
        normalized_result = to_jsonable(raw_result)

        return {
            "tool_name": tool_name,
            "service": service_name,
            "arguments": parameters or {},
            "result": normalized_result,
            "text": extract_tool_text(raw_result),
        }


async def test_login() -> None:
    """Run the shared OAuth flow and print the discovered tools."""

    print("=" * 50)
    print("  SWIGGY MCP LOGIN")
    print("=" * 50)

    client = SwiggyMCPClient()
    await client.connect()
    try:
        tools = await client.list_tools()
        print(f"\nLogin successful! Found {len(tools)} tools:")
        for tool in tools:
            description = tool.description[:60] if tool.description else ""
            print(f"  - {tool.name}: {description}")
    finally:
        await client.disconnect()

    print(f"\nTokens saved to: {TOKEN_FILE}")
    print("You can now run the hosted backend or legacy agent.\n")
