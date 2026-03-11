from pathlib import Path

import pytest

from reels_backend.agent_worker import (
    _extract_dispatch_metadata,
    _validate_eleven_realtime_stt_runtime,
    build_agent_for_avatar,
    build_lemonslice_session_kwargs,
)
from reels_backend.config import Settings
from reels_backend.registry import AvatarEntry


def test_build_lemonslice_kwargs_for_image_url() -> None:
    avatar = AvatarEntry.model_validate(
        {
            "avatar_id": "easy",
            "display_name": "Easy",
            "system_prompt": "Hello",
            "lemonslice": {"type": "image_url", "value": "https://example.com/easy.png"},
            "avatar_motion_prompt": "natural movement",
            "is_active": True,
        }
    )

    kwargs = build_lemonslice_session_kwargs(avatar)
    assert kwargs["agent_image_url"] == "https://example.com/easy.png"
    assert kwargs["agent_prompt"] == "natural movement"
    assert "agent_id" not in kwargs


def test_build_lemonslice_kwargs_for_agent_id() -> None:
    avatar = AvatarEntry.model_validate(
        {
            "avatar_id": "easy",
            "display_name": "Easy",
            "system_prompt": "Hello",
            "lemonslice": {"type": "agent_id", "value": "agent_123"},
            "avatar_motion_prompt": "natural movement",
            "is_active": True,
        }
    )

    kwargs = build_lemonslice_session_kwargs(avatar)
    assert kwargs["agent_id"] == "agent_123"
    assert kwargs["agent_prompt"] == "natural movement"
    assert "agent_image_url" not in kwargs


def test_extract_dispatch_metadata_prefers_metadata_values() -> None:
    class FakeJob:
        metadata = '{"avatar_id":"shirley","switch_id":"abc-123"}'

    class FakeContext:
        job = FakeJob()

    avatar_id, switch_id = _extract_dispatch_metadata(FakeContext())  # type: ignore[arg-type]
    assert avatar_id == "shirley"
    assert switch_id == "abc-123"


def test_extract_dispatch_metadata_handles_invalid_json() -> None:
    class FakeJob:
        metadata = "not-json"

    class FakeContext:
        job = FakeJob()

    avatar_id, switch_id = _extract_dispatch_metadata(FakeContext())  # type: ignore[arg-type]
    assert avatar_id == ""
    assert switch_id == "initial"


@pytest.mark.asyncio
async def test_stt_runtime_validation_fails_fast_for_non_realtime_model() -> None:
    settings = Settings(
        livekit_api_key="livekit_key",
        livekit_api_secret="livekit_secret",
        livekit_url="wss://example.livekit.cloud",
        agent_name="lemonslice-salary-coach",
        mistral_api_key="mistral",
        eleven_api_key="eleven",
        lemonslice_api_key="lemonslice",
        mistral_model="mistral-medium-latest",
        eleven_stt_model="scribe_v2",
        eleven_tts_model="eleven_turbo_v2_5",
        eleven_tts_voice_id="voice",
        eleven_tts_streaming_latency=4,
        eleven_tts_sync_alignment=False,
        eleven_language_code="en",
        eleven_validate_stt_runtime=False,
        eleven_server_vad_enabled=True,
        eleven_server_vad_threshold=0.72,
        eleven_server_vad_silence_threshold_secs=0.45,
        eleven_server_vad_min_speech_duration_ms=420,
        eleven_server_vad_min_silence_duration_ms=500,
        token_ttl_minutes=15,
        idle_silence_seconds=7,
        vad_activation_threshold=0.72,
        vad_deactivation_threshold=0.60,
        vad_min_speech_seconds=0.25,
        vad_min_silence_seconds=0.85,
        vad_prefix_padding_seconds=0.35,
        min_endpointing_delay=0.6,
        max_endpointing_delay=1.9,
        preemptive_generation=True,
        allow_interruptions=True,
        min_interruption_duration=0.9,
        min_interruption_words=2,
        worker_num_idle_processes=1,
        avatar_registry_path=Path("/tmp/avatars.yaml"),
    )

    with pytest.raises(RuntimeError, match="ELEVEN_STT_MODEL must be 'scribe_v2_realtime'"):
        await _validate_eleven_realtime_stt_runtime(settings)


def test_build_agent_for_avatar_has_no_swiggy_tools() -> None:
    poke = AvatarEntry.model_validate(
        {
            "avatar_id": "poke",
            "display_name": "Her",
            "system_prompt": "Hello",
            "lemonslice": {"type": "agent_id", "value": "agent_123"},
            "is_active": True,
        }
    )
    shirley = AvatarEntry.model_validate(
        {
            "avatar_id": "shirley",
            "display_name": "Shirley",
            "system_prompt": "Hello",
            "lemonslice": {"type": "agent_id", "value": "agent_456"},
            "is_active": True,
        }
    )

    poke_agent = build_agent_for_avatar(poke)
    shirley_agent = build_agent_for_avatar(shirley)

    poke_tool_names = {tool.info.name for tool in poke_agent.tools if hasattr(tool, "info")}
    shirley_tool_names = {
        tool.info.name for tool in shirley_agent.tools if hasattr(tool, "info")
    }

    assert "swiggy_mcp_call" not in poke_tool_names
    assert "swiggy_prepare_order_confirmation" not in poke_tool_names
    assert "swiggy_mcp_call" not in shirley_tool_names
