from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class RegistryValidationError(RuntimeError):
    """Raised when avatar registry content is invalid."""


class LemonSliceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    """LemonSlice avatar source. Only this is sent to LemonSlice/LiveKit—never preview_image_url.
    - image_url: value is a URL; LemonSlice uses it to render the avatar.
    - agent_id: value is a LemonSlice agent ID; avatar is fully driven by LemonSlice (no image URL)."""
    type: Literal["image_url", "agent_id"]
    value: str = Field(min_length=1)

    @field_validator("value")
    @classmethod
    def non_empty_value(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("lemonslice.value must be non-empty")
        return stripped


class AvatarEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    avatar_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    lemonslice: LemonSliceRef
    # Optional; for frontend only (feed/profile thumbnails). Never sent to LiveKit or LemonSlice.
    # When lemonslice.type is agent_id, you typically omit this; UI can show a placeholder.
    preview_image_url: str | None = None
    profile_image_urls: list[str] = Field(default_factory=list)
    avatar_motion_prompt: str = (
        "Natural conversational body language. Keep movements subtle and human-like."
    )
    tts_voice_id: str | None = None  # ElevenLabs voice_id; if unset, uses ELEVEN_TTS_VOICE_ID
    caption: str | None = None  # Feed caption; if unset, frontend falls back to display_name
    opening_line: str | None = None  # Optional first line spoken by avatar when session starts
    is_active: bool = True

    @field_validator("avatar_id", "display_name", "system_prompt", "avatar_motion_prompt")
    @classmethod
    def non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text field must be non-empty")
        return stripped

    @field_validator("opening_line")
    @classmethod
    def non_empty_opening_line(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("opening_line must be non-empty when provided")
        return stripped


class AvatarRegistryData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    avatars: list[AvatarEntry]

    @model_validator(mode="after")
    def validate_unique_avatar_ids(self) -> "AvatarRegistryData":
        ids = [avatar.avatar_id for avatar in self.avatars]
        if len(ids) != len(set(ids)):
            raise ValueError("avatar_id values must be unique")
        return self


@dataclass(frozen=True)
class PublicAvatar:
    avatar_id: str
    display_name: str
    preview_image_url: str | None
    profile_image_urls: tuple[str, ...]
    caption: str | None
    is_active: bool


class AvatarRegistry:
    def __init__(self, data: AvatarRegistryData) -> None:
        self._data = data
        self._by_id = {avatar.avatar_id: avatar for avatar in data.avatars}

    @classmethod
    def from_path(cls, path: Path) -> "AvatarRegistry":
        if not path.exists():
            raise RegistryValidationError(f"Avatar registry file not found: {path}")

        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            raise RegistryValidationError(f"Invalid YAML in avatar registry: {error}") from error

        if payload is None:
            payload = {}

        try:
            data = AvatarRegistryData.model_validate(payload)
        except ValidationError as error:
            raise RegistryValidationError(f"Invalid avatar registry schema: {error}") from error

        return cls(data)

    def get(self, avatar_id: str) -> AvatarEntry | None:
        return self._by_id.get(avatar_id)

    def all(self) -> list[AvatarEntry]:
        return list(self._data.avatars)

    def all_public(self) -> list[PublicAvatar]:
        return [
            PublicAvatar(
                avatar_id=avatar.avatar_id,
                display_name=avatar.display_name,
                preview_image_url=avatar.preview_image_url,
                profile_image_urls=tuple(avatar.profile_image_urls),
                caption=avatar.caption,
                is_active=avatar.is_active,
            )
            for avatar in self._data.avatars
        ]
