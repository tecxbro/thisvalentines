from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import aiohttp

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AutoSubscribe,
    JobContext,
    cli,
    room_io,
)
from livekit.agents.voice.events import CloseEvent
from livekit.plugins import elevenlabs, lemonslice, mistralai, silero

from .config import Settings, get_settings, load_env_files
from .registry import AvatarEntry, AvatarRegistry

logger = logging.getLogger("valentines-reels-worker")
logger.setLevel(logging.INFO)

load_env_files()
DEFAULT_AGENT_NAME = os.getenv("AGENT_NAME", "lemonslice-salary-coach")
INITIAL_SWITCH_ID = "initial"
ELEVEN_REQUIRED_REALTIME_STT_MODEL = "scribe_v2_realtime"


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


server = AgentServer(num_idle_processes=_int_env("WORKER_NUM_IDLE_PROCESSES", 1))


@dataclass
class UserData:
    ctx: JobContext | None = None
    avatar_id: str = ""
    switch_id: str = INITIAL_SWITCH_ID
    user_id: str = ""


class ReelsAvatarAgent(Agent):
    def __init__(self, avatar: AvatarEntry, *, extra_instructions: str | None = None) -> None:
        self._avatar = avatar
        persona_lock = (
            f"You are avatar_id='{avatar.avatar_id}' and display_name='{avatar.display_name}'. "
            "Stay in this persona consistently for every reply in this session."
        )
        instructions = f"{persona_lock}\n\n{avatar.system_prompt}"
        if extra_instructions:
            instructions = f"{instructions}\n\n{extra_instructions}"
        super().__init__(instructions=instructions)

    async def on_enter(self) -> None:
        userdata: UserData = self.session.userdata

        if userdata.ctx and userdata.ctx.room:
            await userdata.ctx.room.local_participant.set_attributes(
                {
                    "avatar_id": self._avatar.avatar_id,
                    "display_name": self._avatar.display_name,
                }
            )

    async def on_exit(self) -> None:
        pass


def build_agent_for_avatar(avatar: AvatarEntry) -> Agent:
    return ReelsAvatarAgent(avatar)


def _event_summary(payload: Any) -> str:
    if isinstance(payload, str):
        return payload

    for attr in ("text", "transcript", "content"):
        value = getattr(payload, attr, None)
        if isinstance(value, str) and value.strip():
            return value

    return str(payload)


def build_lemonslice_session_kwargs(avatar: AvatarEntry) -> dict[str, str]:
    """Build kwargs for LemonSlice AvatarSession. Uses only lemonslice (agent_id or image_url);
    preview_image_url is never passed—it is for frontend display only."""
    kwargs: dict[str, str] = {
        "agent_prompt": avatar.avatar_motion_prompt,
    }
    if avatar.lemonslice.type == "image_url":
        kwargs["agent_image_url"] = avatar.lemonslice.value
    else:
        kwargs["agent_id"] = avatar.lemonslice.value
    return kwargs


def resolve_avatar(avatar_id: str) -> AvatarEntry:
    registry = get_registry()
    avatar = registry.get(avatar_id)
    if avatar and avatar.is_active:
        return avatar

    fallback = next((item for item in registry.all() if item.is_active), None)
    if not fallback:
        raise RuntimeError("No active avatars available in registry")

    logger.warning(
        "Avatar '%s' not found or inactive, falling back to '%s'",
        avatar_id,
        fallback.avatar_id,
    )
    return fallback


@lru_cache
def get_worker_settings() -> Settings:
    settings = get_settings()
    # Some plugins read credentials from env by default.
    os.environ.setdefault("LEMONSLICE_API_KEY", settings.lemonslice_api_key)
    os.environ.setdefault("MISTRAL_API_KEY", settings.mistral_api_key)
    os.environ.setdefault("ELEVEN_API_KEY", settings.eleven_api_key)
    return settings


@lru_cache
def get_registry() -> AvatarRegistry:
    settings = get_worker_settings()
    return AvatarRegistry.from_path(settings.avatar_registry_path)


@lru_cache
def get_vad():
    settings = get_worker_settings()
    return silero.VAD.load(
        min_speech_duration=settings.vad_min_speech_seconds,
        min_silence_duration=settings.vad_min_silence_seconds,
        prefix_padding_duration=settings.vad_prefix_padding_seconds,
        activation_threshold=settings.vad_activation_threshold,
        deactivation_threshold=settings.vad_deactivation_threshold,
    )


_stt_runtime_validated = False
_stt_runtime_validation_lock = asyncio.Lock()
_voice_ids_cache: set[str] | None = None
_voice_ids_cache_expires_at: float = 0.0
_voice_ids_cache_lock = asyncio.Lock()


async def _validate_eleven_realtime_stt_runtime(settings: Settings) -> None:
    """Fail fast when Eleven STT runtime config does not support LiveKit realtime streaming."""
    if settings.eleven_stt_model != ELEVEN_REQUIRED_REALTIME_STT_MODEL:
        raise RuntimeError(
            "ELEVEN_STT_MODEL must be 'scribe_v2_realtime' for livekit-plugins-elevenlabs 1.4.x"
        )

    async with aiohttp.ClientSession() as http_session:
        stt = elevenlabs.STT(
            api_key=settings.eleven_api_key,
            model_id=settings.eleven_stt_model,
            language_code=settings.eleven_language_code,
            http_session=http_session,
        )
        stream = stt.stream()
        ws: aiohttp.ClientWebSocketResponse | None = None
        try:
            ws = await stream._connect_ws()  # type: ignore[attr-defined]
            first_msg = await asyncio.wait_for(ws.receive_json(), timeout=8)
            msg_type = first_msg.get("message_type")
            if msg_type in {"invalid_request", "auth_error", "error"}:
                detail = first_msg.get("error") or first_msg.get("message") or "unknown error"
                raise RuntimeError(
                    "ELEVEN_STT_MODEL must be 'scribe_v2_realtime' for livekit-plugins-elevenlabs 1.4.x "
                    f"(runtime replied: {msg_type}: {detail})"
                )
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(
                "Failed ElevenLabs STT realtime startup validation. "
                "Ensure ELEVEN_API_KEY is valid and ELEVEN_STT_MODEL is 'scribe_v2_realtime'."
            ) from exc
        finally:
            if ws is not None and not ws.closed:
                await ws.close()
            await stream.aclose()
            await stt.aclose()


async def ensure_stt_runtime_validated(settings: Settings) -> None:
    global _stt_runtime_validated
    if _stt_runtime_validated:
        return

    async with _stt_runtime_validation_lock:
        if _stt_runtime_validated:
            return
        await _validate_eleven_realtime_stt_runtime(settings)
        _stt_runtime_validated = True
        logger.info("Eleven STT realtime runtime validation passed")


def _extract_dispatch_metadata(ctx: JobContext) -> tuple[str, str]:
    requested_avatar_id = ""
    switch_id = INITIAL_SWITCH_ID

    metadata = getattr(ctx.job, "metadata", None)
    if not metadata:
        return requested_avatar_id, switch_id

    try:
        parsed = json.loads(metadata)
    except (json.JSONDecodeError, TypeError):
        return requested_avatar_id, switch_id

    if isinstance(parsed, dict):
        avatar_id = parsed.get("avatar_id", "")
        if isinstance(avatar_id, str):
            requested_avatar_id = avatar_id.strip()

        parsed_switch_id = parsed.get("switch_id", "")
        if isinstance(parsed_switch_id, str) and parsed_switch_id.strip():
            switch_id = parsed_switch_id.strip()

    return requested_avatar_id, switch_id


async def _fetch_eleven_voice_ids(settings: Settings) -> set[str]:
    url = "https://api.elevenlabs.io/v1/voices"
    headers = {"xi-api-key": settings.eleven_api_key}
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as http_session:
        async with http_session.get(url, headers=headers) as response:
            if response.status != 200:
                body = await response.text()
                raise RuntimeError(
                    f"Eleven voice list request failed status={response.status} body={body[:200]}"
                )
            payload = await response.json()

    voices = payload.get("voices", [])
    return {
        voice.get("voice_id")
        for voice in voices
        if isinstance(voice, dict) and isinstance(voice.get("voice_id"), str)
    }


async def _get_cached_eleven_voice_ids(settings: Settings) -> set[str]:
    global _voice_ids_cache, _voice_ids_cache_expires_at

    now = time.monotonic()
    if _voice_ids_cache is not None and now < _voice_ids_cache_expires_at:
        return _voice_ids_cache

    async with _voice_ids_cache_lock:
        now = time.monotonic()
        if _voice_ids_cache is not None and now < _voice_ids_cache_expires_at:
            return _voice_ids_cache
        voice_ids = await _fetch_eleven_voice_ids(settings)
        _voice_ids_cache = voice_ids
        _voice_ids_cache_expires_at = now + 600
        return voice_ids


async def _resolve_selected_voice_id(settings: Settings, avatar: AvatarEntry) -> str:
    selected_voice_id = avatar.tts_voice_id or settings.eleven_tts_voice_id
    if not avatar.tts_voice_id:
        return selected_voice_id
    if selected_voice_id == settings.eleven_tts_voice_id:
        return selected_voice_id

    try:
        available_voice_ids = await _get_cached_eleven_voice_ids(settings)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Unable to verify Eleven voice_id='%s'; continuing with configured value (%s)",
            selected_voice_id,
            exc,
        )
        return selected_voice_id

    if selected_voice_id not in available_voice_ids:
        logger.warning(
            "Configured avatar voice_id='%s' is unavailable for current ELEVEN_API_KEY. "
            "Falling back to ELEVEN_TTS_VOICE_ID='%s'.",
            selected_voice_id,
            settings.eleven_tts_voice_id,
        )
        return settings.eleven_tts_voice_id
    return selected_voice_id


async def _publish_agent_ready(ctx: JobContext, avatar_id: str, switch_id: str) -> None:
    payload = json.dumps(
        {
            "type": "reels.agent_ready",
            "avatar_id": avatar_id,
            "switch_id": switch_id,
        }
    ).encode("utf-8")
    await ctx.room.local_participant.publish_data(
        payload,
        reliable=True,
        topic="reels.events",
    )


@server.rtc_session(agent_name=DEFAULT_AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    settings = get_worker_settings()
    logger.info(
        "Worker session started for agent='%s' room='%s'",
        settings.agent_name,
        getattr(ctx.room, "name", ""),
    )

    try:
        if settings.eleven_stt_model != ELEVEN_REQUIRED_REALTIME_STT_MODEL:
            raise RuntimeError(
                "ELEVEN_STT_MODEL must be 'scribe_v2_realtime' for livekit-plugins-elevenlabs 1.4.x"
            )

        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
        participant = await ctx.wait_for_participant()

        if settings.eleven_validate_stt_runtime:
            await ensure_stt_runtime_validated(settings)

        requested_avatar_id, switch_id = _extract_dispatch_metadata(ctx)
        if not requested_avatar_id:
            requested_avatar_id = participant.attributes.get("avatar_id", "")
        avatar = resolve_avatar(requested_avatar_id)
        prompt_sha = hashlib.sha1(avatar.system_prompt.encode("utf-8")).hexdigest()[:12]
        logger.info(
            "Resolved avatar_id=%s switch_id=%s participant=%s prompt_sha=%s",
            avatar.avatar_id,
            switch_id,
            getattr(participant, "identity", ""),
            prompt_sha,
        )
        selected_voice_id = await _resolve_selected_voice_id(settings, avatar)
        logger.info(
            "Voice pipeline config stt_model=%s tts_model=%s tts_voice_id=%s tts_streaming_latency=%s sync_alignment=%s",
            settings.eleven_stt_model,
            settings.eleven_tts_model,
            selected_voice_id,
            settings.eleven_tts_streaming_latency,
            settings.eleven_tts_sync_alignment,
        )
        logger.info(
            "Turn config allow_interruptions=%s min_interruption_duration=%.2f min_interruption_words=%s "
            "endpointing=[%.2f, %.2f] eleven_server_vad_enabled=%s",
            settings.allow_interruptions,
            settings.min_interruption_duration,
            settings.min_interruption_words,
            settings.min_endpointing_delay,
            settings.max_endpointing_delay,
            settings.eleven_server_vad_enabled,
        )

        tts_kwargs: dict[str, Any] = {
            "api_key": settings.eleven_api_key,
            "voice_id": selected_voice_id,
            "model": settings.eleven_tts_model,
            "language": settings.eleven_language_code,
            "sync_alignment": settings.eleven_tts_sync_alignment,
        }
        if settings.eleven_tts_streaming_latency is not None:
            tts_kwargs["streaming_latency"] = settings.eleven_tts_streaming_latency

        stt_kwargs: dict[str, Any] = {
            "api_key": settings.eleven_api_key,
            "model_id": settings.eleven_stt_model,
            "language_code": settings.eleven_language_code,
            "tag_audio_events": False,
        }
        if settings.eleven_server_vad_enabled:
            stt_kwargs["server_vad"] = {
                "vad_threshold": settings.eleven_server_vad_threshold,
                "vad_silence_threshold_secs": settings.eleven_server_vad_silence_threshold_secs,
                "min_speech_duration_ms": settings.eleven_server_vad_min_speech_duration_ms,
                "min_silence_duration_ms": settings.eleven_server_vad_min_silence_duration_ms,
            }

        userdata = UserData(
            ctx=ctx,
            avatar_id=avatar.avatar_id,
            switch_id=switch_id,
            user_id=getattr(participant, "identity", ""),
        )

        session = AgentSession[UserData](
            vad=get_vad(),
            min_endpointing_delay=settings.min_endpointing_delay,
            max_endpointing_delay=settings.max_endpointing_delay,
            stt=elevenlabs.STT(**stt_kwargs),
            llm=mistralai.LLM(
                api_key=settings.mistral_api_key,
                model=settings.mistral_model,
            ),
            tts=elevenlabs.TTS(**tts_kwargs),
            allow_interruptions=settings.allow_interruptions,
            min_interruption_duration=settings.min_interruption_duration,
            min_interruption_words=settings.min_interruption_words,
            resume_false_interruption=False,
            preemptive_generation=settings.preemptive_generation,
            userdata=userdata,
        )

        def _log_user_speech_committed(event_payload: Any) -> None:
            logger.info(
                "user_speech_committed avatar_id=%s switch_id=%s text=%s",
                userdata.avatar_id,
                userdata.switch_id,
                _event_summary(event_payload),
            )

        def _log_agent_speech_committed(event_payload: Any) -> None:
            logger.info(
                "agent_speech_committed avatar_id=%s switch_id=%s text=%s",
                userdata.avatar_id,
                userdata.switch_id,
                _event_summary(event_payload),
            )

        session.on("user_speech_committed", _log_user_speech_committed)
        session.on("agent_speech_committed", _log_agent_speech_committed)

        avatar_session = lemonslice.AvatarSession(**build_lemonslice_session_kwargs(avatar))
        await avatar_session.start(session, room=ctx.room)

        def on_data_received(data_packet) -> None:
            try:
                payload = data_packet.data if hasattr(data_packet, "data") else data_packet
                if not isinstance(payload, bytes):
                    return

                msg: dict[str, Any] = json.loads(payload.decode("utf-8"))
                if msg.get("type") != "reels.agent_leave":
                    return

                target_switch_id = msg.get("target_switch_id", "")
                if isinstance(target_switch_id, str) and target_switch_id:
                    if target_switch_id != userdata.switch_id:
                        return

                logger.info(
                    "Received reels.agent_leave for switch_id=%s target_switch_id=%s; shutting down",
                    userdata.switch_id,
                    target_switch_id,
                )
                session.input.set_audio_enabled(False)
                session.shutdown(drain=False)
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
                pass

        ctx.room.on("data_received", on_data_received)
        close_event = asyncio.Event()

        def _on_session_close(ev: CloseEvent) -> None:
            logger.info(
                "Session closed reason=%s error=%s",
                ev.reason.value if hasattr(ev.reason, "value") else str(ev.reason),
                str(ev.error) if ev.error else None,
            )
            close_event.set()

        session.on("close", _on_session_close)

        await session.start(
            agent=build_agent_for_avatar(avatar),
            room=ctx.room,
            room_options=room_io.RoomOptions(
                delete_room_on_close=False,
            ),
        )

        await _publish_agent_ready(
            ctx=ctx,
            avatar_id=avatar.avatar_id,
            switch_id=userdata.switch_id,
        )

        if avatar.opening_line:
            session.say(
                avatar.opening_line,
                allow_interruptions=True,
                add_to_chat_ctx=True,
            )

        await close_event.wait()
    except Exception as e:  # noqa: BLE001
        logger.exception("Worker entrypoint failed")
        raise


if __name__ == "__main__":
    cli.run_app(server)
