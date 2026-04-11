"""FastAPI entrypoint for the hosted LemonSlice + Swiggy sidecar runtime."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .mistral_client import MistralTextClient
from .orchestrator import SwiggyDecisionEngine, SwiggyRealtimeOrchestrator

APP_ROOT = Path(__file__).resolve().parents[1]
SWIGGY_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]
LEGACY_BACKEND_ROOT = REPO_ROOT / "backend"


def load_env_files() -> None:
    """Load app-local env files first, then fall back to shared backend envs."""
    for path in (
        APP_ROOT / ".env.local",
        APP_ROOT / ".env",
        LEGACY_BACKEND_ROOT / ".env.local",
        SWIGGY_ROOT / ".env",
    ):
        if path.exists():
            load_dotenv(path, override=False)


load_env_files()

LEMONSLICE_CREATE_ROOM_ENDPOINT = os.getenv(
    "LEMONSLICE_CREATE_ROOM_ENDPOINT",
    "https://lemonslice.com/api/liveai/rooms",
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_runtime: dict[str, Any] = {}


class CreateRoomResponse(BaseModel):
    """Response payload returned after creating a LemonSlice hosted room."""

    room_url: str
    token: str
    image_url: str | None = None
    session_id: str


class TranscriptRequest(BaseModel):
    """Bridge payload sent from the browser into the Swiggy sidecar."""

    session_id: str = Field(min_length=1)
    transcription: str = Field(min_length=1)
    event_type: str = "user_transcription"
    client_timestamp: str | None = None


class TranscriptResponse(BaseModel):
    """Normal sidecar response consumed by the hosted frontend bridge."""

    action: str
    reason: str
    service: str | None = None
    message: str | None = None
    chat_message: str | None = None
    flow_open: bool | None = None


class DebugTranscriptResponse(TranscriptResponse):
    """Extended sidecar response that includes planner and tool trace data."""

    debug_trace: dict[str, Any] | None = None


def _require_env(name: str) -> str:
    """Fetch a required environment variable or raise a FastAPI 500 error."""
    value = os.getenv(name)
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing required environment variable: {name}")
    return value


def _pick_first(payload: dict[str, Any], *keys: str) -> Any:
    """Return the first non-null value among a set of possible response keys."""
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _get_orchestrator() -> SwiggyRealtimeOrchestrator:
    """Lazily build and cache the sidecar orchestrator and MCP client."""
    orchestrator = _runtime.get("orchestrator")
    if orchestrator is not None:
        return orchestrator

    if str(SWIGGY_ROOT) not in sys.path:
        sys.path.insert(0, str(SWIGGY_ROOT))

    # The hosted backend reuses the shared Swiggy MCP client from the parent app
    # so the legacy and hosted runtimes stay on the same OAuth/tool layer.
    from swiggy_mcp_client import SwiggyMCPClient

    planner_client = MistralTextClient(
        api_key=_require_env("MISTRAL_API_KEY"),
        model=os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
    )
    swiggy_client = SwiggyMCPClient()
    decision_engine = SwiggyDecisionEngine(
        swiggy_client=swiggy_client,
        planner_client=planner_client,
    )
    orchestrator = SwiggyRealtimeOrchestrator(decision_engine=decision_engine)
    _runtime["orchestrator"] = orchestrator
    _runtime["swiggy_client"] = swiggy_client
    return orchestrator


@app.post("/create-room", response_model=CreateRoomResponse)
async def create_room() -> CreateRoomResponse:
    """Create a LemonSlice hosted room and normalize the returned payload."""
    agent_id = _require_env("LEMONSLICE_AGENT_ID")
    api_key = _require_env("LEMONSLICE_API_KEY")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                LEMONSLICE_CREATE_ROOM_ENDPOINT,
                headers={
                    "X-API-Key": api_key,
                    "Content-Type": "application/json",
                },
                json={"agent_id": agent_id},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=500, detail="Failed to create LemonSlice room") from exc

    data = response.json()
    room_url = _pick_first(data, "room_url", "roomUrl")
    token = _pick_first(data, "token", "room_token", "roomToken")
    session_id = _pick_first(data, "session_id", "sessionId")
    image_url = _pick_first(data, "image_url", "imageUrl")

    if not room_url or not token or not session_id:
        raise HTTPException(
            status_code=500,
            detail="LemonSlice room response was missing room_url, token, or session_id",
        )

    return CreateRoomResponse(
        room_url=room_url,
        token=token,
        image_url=image_url,
        session_id=session_id,
    )


@app.post("/swiggy/transcript", response_model=TranscriptResponse)
async def handle_swiggy_transcript(payload: TranscriptRequest) -> TranscriptResponse:
    """Handle the normal hosted transcript bridge used by the live avatar flow."""
    orchestrator = _get_orchestrator()
    result = await orchestrator.handle_transcript(
        session_id=payload.session_id,
        transcription=payload.transcription,
        event_type=payload.event_type,
        client_timestamp=payload.client_timestamp,
    )
    return TranscriptResponse(**result)


@app.post("/swiggy/debug-transcript", response_model=DebugTranscriptResponse)
async def handle_swiggy_debug_transcript(payload: TranscriptRequest) -> DebugTranscriptResponse:
    """Expose the same sidecar path with extra debug trace data for local testing."""
    orchestrator = _get_orchestrator()
    result = await orchestrator.handle_transcript(
        session_id=payload.session_id,
        transcription=payload.transcription,
        event_type=payload.event_type,
        client_timestamp=payload.client_timestamp,
        include_debug_trace=True,
    )
    return DebugTranscriptResponse(**result)


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Disconnect the shared MCP client when the FastAPI process exits."""
    swiggy_client = _runtime.get("swiggy_client")
    if swiggy_client is not None:
        await swiggy_client.disconnect()
