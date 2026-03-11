from datetime import UTC, datetime
from pathlib import Path

import jwt

from reels_backend.config import Settings
from reels_backend.token_service import issue_connection_details


def build_settings() -> Settings:
    return Settings(
        livekit_api_key="devkey",
        livekit_api_secret="devsecret",
        livekit_url="wss://example.livekit.cloud",
        agent_name="valentines-reels-agent",
        mistral_api_key="mistral",
        eleven_api_key="eleven",
        lemonslice_api_key="lemonslice",
        mistral_model="mistral-medium-latest",
        eleven_stt_model="scribe_v2_realtime",
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


def test_token_contains_avatar_attributes_and_agent_dispatch() -> None:
    settings = build_settings()
    details = issue_connection_details(settings=settings, avatar_id="easy")

    payload = jwt.decode(
        details.participant_token,
        options={"verify_signature": False},
        algorithms=["HS256"],
    )

    attributes = payload.get("attributes", {})
    assert attributes.get("avatar_id") == "easy"

    room_config = payload.get("roomConfig", {})
    agents = room_config.get("agents", [])
    assert agents
    assert agents[0].get("agentName") == settings.agent_name

    assert payload.get("video", {}).get("room") == details.room_name
    assert payload.get("video", {}).get("roomJoin") is True


def test_token_expiry_in_future() -> None:
    settings = build_settings()
    details = issue_connection_details(settings=settings, avatar_id="easy")

    assert details.expires_at > datetime.now(UTC)
