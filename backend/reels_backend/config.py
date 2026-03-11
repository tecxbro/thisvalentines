from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def load_env_files() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env_local = project_root / ".env.local"

    if env_local.exists():
        load_dotenv(env_local, override=False)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _required_env_any(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    joined = ", ".join(names)
    raise RuntimeError(f"Missing required environment variable (one of): {joined}")


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as error:
        raise RuntimeError(f"Environment variable {name} must be an integer") from error


def _optional_int_env(name: str, default: int | None) -> int | None:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"", "none", "null"}:
        return None

    try:
        return int(normalized)
    except ValueError as error:
        raise RuntimeError(f"Environment variable {name} must be an integer or empty") from error


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as error:
        raise RuntimeError(f"Environment variable {name} must be a float") from error


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Environment variable {name} must be a boolean")


@dataclass(frozen=True)
class Settings:
    livekit_api_key: str
    livekit_api_secret: str
    livekit_url: str
    agent_name: str
    mistral_api_key: str
    eleven_api_key: str
    lemonslice_api_key: str
    mistral_model: str
    eleven_stt_model: str
    eleven_tts_model: str
    eleven_tts_voice_id: str
    eleven_tts_streaming_latency: int | None
    eleven_tts_sync_alignment: bool
    eleven_language_code: str
    eleven_validate_stt_runtime: bool
    eleven_server_vad_enabled: bool
    eleven_server_vad_threshold: float
    eleven_server_vad_silence_threshold_secs: float
    eleven_server_vad_min_speech_duration_ms: int
    eleven_server_vad_min_silence_duration_ms: int
    token_ttl_minutes: int
    idle_silence_seconds: int
    vad_activation_threshold: float
    vad_deactivation_threshold: float
    vad_min_speech_seconds: float
    vad_min_silence_seconds: float
    vad_prefix_padding_seconds: float
    min_endpointing_delay: float
    max_endpointing_delay: float
    preemptive_generation: bool
    allow_interruptions: bool
    min_interruption_duration: float
    min_interruption_words: int
    worker_num_idle_processes: int
    avatar_registry_path: Path


@lru_cache
def get_settings() -> Settings:
    load_env_files()

    project_root = Path(__file__).resolve().parents[1]
    registry_path = Path(
        os.getenv("AVATAR_REGISTRY_PATH", str(project_root / "avatar_registry.yaml"))
    )
    if not registry_path.is_absolute():
        registry_path = (project_root / registry_path).resolve()

    return Settings(
        livekit_api_key=_required_env("LIVEKIT_API_KEY"),
        livekit_api_secret=_required_env("LIVEKIT_API_SECRET"),
        livekit_url=_required_env("LIVEKIT_URL"),
        agent_name=os.getenv("AGENT_NAME", "lemonslice-salary-coach"),
        mistral_api_key=_required_env("MISTRAL_API_KEY"),
        eleven_api_key=_required_env_any("ELEVEN_API_KEY", "ELEVENLABS_API_KEY"),
        lemonslice_api_key=_required_env("LEMONSLICE_API_KEY"),
        mistral_model=os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
        eleven_stt_model=os.getenv("ELEVEN_STT_MODEL", "scribe_v2_realtime"),
        eleven_tts_model=os.getenv("ELEVEN_TTS_MODEL", "eleven_turbo_v2_5"),
        eleven_tts_voice_id=os.getenv("ELEVEN_TTS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),
        eleven_tts_streaming_latency=_optional_int_env("ELEVEN_TTS_STREAMING_LATENCY", 4),
        eleven_tts_sync_alignment=_bool_env("ELEVEN_TTS_SYNC_ALIGNMENT", False),
        eleven_language_code=os.getenv("ELEVEN_LANGUAGE_CODE", "en"),
        eleven_validate_stt_runtime=_bool_env("ELEVEN_VALIDATE_STT_RUNTIME", False),
        eleven_server_vad_enabled=_bool_env("ELEVEN_SERVER_VAD_ENABLED", True),
        eleven_server_vad_threshold=_float_env("ELEVEN_SERVER_VAD_THRESHOLD", 0.72),
        eleven_server_vad_silence_threshold_secs=_float_env(
            "ELEVEN_SERVER_VAD_SILENCE_THRESHOLD_SECS", 0.45
        ),
        eleven_server_vad_min_speech_duration_ms=_int_env(
            "ELEVEN_SERVER_VAD_MIN_SPEECH_DURATION_MS", 420
        ),
        eleven_server_vad_min_silence_duration_ms=_int_env(
            "ELEVEN_SERVER_VAD_MIN_SILENCE_DURATION_MS", 500
        ),
        token_ttl_minutes=_int_env("TOKEN_TTL_MINUTES", 15),
        idle_silence_seconds=_int_env("IDLE_SILENCE_SECONDS", 7),
        vad_activation_threshold=_float_env("VAD_ACTIVATION_THRESHOLD", 0.80),
        vad_deactivation_threshold=_float_env("VAD_DEACTIVATION_THRESHOLD", 0.65),
        vad_min_speech_seconds=_float_env("VAD_MIN_SPEECH_SECONDS", 0.32),
        vad_min_silence_seconds=_float_env("VAD_MIN_SILENCE_SECONDS", 0.45),
        vad_prefix_padding_seconds=_float_env("VAD_PREFIX_PADDING_SECONDS", 0.35),
        min_endpointing_delay=_float_env("MIN_ENDPOINTING_DELAY", 0.12),
        max_endpointing_delay=_float_env("MAX_ENDPOINTING_DELAY", 0.6),
        preemptive_generation=_bool_env("PREEMPTIVE_GENERATION", True),
        allow_interruptions=_bool_env("ALLOW_INTERRUPTIONS", True),
        min_interruption_duration=_float_env("MIN_INTERRUPTION_DURATION", 0.9),
        min_interruption_words=_int_env("MIN_INTERRUPTION_WORDS", 2),
        worker_num_idle_processes=_int_env("WORKER_NUM_IDLE_PROCESSES", 1),
        avatar_registry_path=registry_path,
    )
