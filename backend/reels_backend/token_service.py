from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from livekit import api

from .config import Settings


@dataclass(frozen=True)
class ConnectionDetails:
    server_url: str
    room_name: str
    participant_name: str
    participant_identity: str
    participant_token: str
    expires_at: datetime


def _sanitize_avatar_id(avatar_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "-" for ch in avatar_id.lower())


def issue_connection_details(
    *,
    settings: Settings,
    avatar_id: str,
    participant_name: str = "user",
) -> ConnectionDetails:
    now = datetime.now(UTC)
    ttl = timedelta(minutes=settings.token_ttl_minutes)
    expires_at = now + ttl

    avatar_slug = _sanitize_avatar_id(avatar_id)
    random_part = uuid4().hex[:12]

    room_name = f"reels_{avatar_slug}_{random_part}"
    participant_identity = f"reels_user_{uuid4().hex[:12]}"

    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(participant_identity)
        .with_name(participant_name)
        .with_ttl(ttl)
        .with_grants(
            api.VideoGrants(
                room=room_name,
                room_join=True,
                can_publish=True,
                can_publish_data=True,
                can_subscribe=True,
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                agents=[api.RoomAgentDispatch(agent_name=settings.agent_name)]
            )
        )
        .with_attributes({"avatar_id": avatar_id})
    )

    participant_token = token.to_jwt()

    return ConnectionDetails(
        server_url=settings.livekit_url,
        room_name=room_name,
        participant_name=participant_name,
        participant_identity=participant_identity,
        participant_token=participant_token,
        expires_at=expires_at,
    )

