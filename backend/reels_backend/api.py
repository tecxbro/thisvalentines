from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from mistralai import Mistral
from pydantic import BaseModel, Field

from livekit import api as livekit_api

from .config import Settings, get_settings
from .registry import AvatarRegistry, RegistryValidationError
from .token_service import issue_connection_details

# In-memory conversation history per thread_id (or default per avatar). Not persisted.
_chat_history: dict[str, list[dict[str, str]]] = {}


class TokenRequest(BaseModel):
    avatar_id: str = Field(min_length=1)


class DispatchAgentRequest(BaseModel):
    room_name: str = Field(min_length=1)
    avatar_id: str = Field(min_length=1)
    switch_id: UUID


class LiveKitTokenResponse(BaseModel):
    provider: Literal["livekit"] = "livekit"
    serverUrl: str
    roomName: str
    participantName: str
    participantIdentity: str
    participantToken: str
    expiresAt: str


class AvatarPublicResponse(BaseModel):
    avatar_id: str
    display_name: str
    preview_image_url: str | None = None
    profile_image_urls: list[str] = Field(default_factory=list)
    caption: str | None = None
    is_active: bool


class AvatarsResponse(BaseModel):
    avatars: list[AvatarPublicResponse]


class ChatRequest(BaseModel):
    avatar_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    thread_id: str | None = None


class ChatResponse(BaseModel):
    reply: str


def _to_iso8601_z(value) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def create_app(
    *,
    settings: Settings | None = None,
    registry: AvatarRegistry | None = None,
) -> FastAPI:
    static_dir = Path(__file__).resolve().parent / "static"

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        if not hasattr(app_instance.state, "settings"):
            app_instance.state.settings = get_settings()

        if not hasattr(app_instance.state, "registry"):
            try:
                app_instance.state.registry = AvatarRegistry.from_path(
                    app_instance.state.settings.avatar_registry_path
                )
            except RegistryValidationError as error:
                raise RuntimeError(f"Registry validation failed: {error}") from error
        yield

    app = FastAPI(title="Valentines Reels Backend", version="0.1.0", lifespan=lifespan)

    if settings is not None:
        app.state.settings = settings
    if registry is not None:
        app.state.registry = registry

    app.mount("/demo-static", StaticFiles(directory=static_dir), name="demo-static")

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "detail": "Invalid request payload",
                "errors": error.errors(),
            },
        )

    @app.get("/demo")
    async def demo() -> FileResponse:
        return FileResponse(static_dir / "reels-demo.html")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        registry: AvatarRegistry = app.state.registry
        return {
            "status": "ok",
            "avatars_loaded": len(registry.all()),
        }

    @app.get("/avatars", response_model=AvatarsResponse)
    async def get_avatars() -> AvatarsResponse:
        registry: AvatarRegistry = app.state.registry
        public = [
            AvatarPublicResponse(
                avatar_id=item.avatar_id,
                display_name=item.display_name,
                preview_image_url=item.preview_image_url,
                profile_image_urls=list(item.profile_image_urls),
                caption=item.caption,
                is_active=item.is_active,
            )
            for item in registry.all_public()
        ]
        return AvatarsResponse(avatars=public)

    @app.post("/token", response_model=LiveKitTokenResponse)
    async def create_token(payload: TokenRequest) -> LiveKitTokenResponse:
        settings_obj: Settings = app.state.settings
        registry_obj: AvatarRegistry = app.state.registry

        avatar = registry_obj.get(payload.avatar_id)
        if avatar is None or not avatar.is_active:
            raise HTTPException(status_code=404, detail="Unknown avatar_id")

        details = issue_connection_details(
            settings=settings_obj,
            avatar_id=avatar.avatar_id,
        )

        return LiveKitTokenResponse(
            provider="livekit",
            serverUrl=details.server_url,
            roomName=details.room_name,
            participantName=details.participant_name,
            participantIdentity=details.participant_identity,
            participantToken=details.participant_token,
            expiresAt=_to_iso8601_z(details.expires_at),
        )

    @app.post("/dispatch-agent", status_code=204)
    async def dispatch_agent(payload: DispatchAgentRequest) -> None:
        settings_obj: Settings = app.state.settings
        registry_obj: AvatarRegistry = app.state.registry

        avatar = registry_obj.get(payload.avatar_id)
        if avatar is None or not avatar.is_active:
            raise HTTPException(status_code=404, detail="Unknown avatar_id")

        lk = livekit_api.LiveKitAPI(
            url=settings_obj.livekit_url,
            api_key=settings_obj.livekit_api_key,
            api_secret=settings_obj.livekit_api_secret,
        )
        try:
            await lk.agent_dispatch.create_dispatch(
                livekit_api.CreateAgentDispatchRequest(
                    room=payload.room_name,
                    agent_name=settings_obj.agent_name,
                    metadata=json.dumps(
                        {
                            "avatar_id": payload.avatar_id,
                            "switch_id": str(payload.switch_id),
                        }
                    ),
                )
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"LiveKit dispatch failed: {exc!s}",
            ) from exc
        finally:
            await lk.aclose()

    @app.post("/chat", response_model=ChatResponse)
    async def chat(payload: ChatRequest) -> ChatResponse:
        registry_obj: AvatarRegistry = app.state.registry
        settings_obj: Settings = app.state.settings

        avatar = registry_obj.get(payload.avatar_id)
        if avatar is None or not avatar.is_active:
            raise HTTPException(status_code=404, detail="Unknown avatar_id")

        thread_key = payload.thread_id or f"default:{payload.avatar_id}"
        history = _chat_history.setdefault(thread_key, [])

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": avatar.system_prompt},
        ]
        for entry in history:
            messages.append({"role": entry["role"], "content": entry["content"]})
        messages.append({"role": "user", "content": payload.message})

        client = Mistral(api_key=settings_obj.mistral_api_key)
        try:
            response = client.chat.complete(
                model=settings_obj.mistral_model,
                messages=messages,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"LLM request failed: {exc!s}",
            ) from exc

        reply_content = ""
        if response.choices and len(response.choices) > 0:
            choice = response.choices[0]
            if choice.message and choice.message.content:
                reply_content = choice.message.content

        history.append({"role": "user", "content": payload.message})
        history.append({"role": "assistant", "content": reply_content})

        return ChatResponse(reply=reply_content)

    return app


app = create_app()
