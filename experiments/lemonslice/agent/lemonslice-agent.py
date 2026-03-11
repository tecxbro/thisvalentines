import asyncio
import io
import json
import logging
import os
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

from livekit.agents import Agent, AgentServer, AgentSession, AutoSubscribe, JobContext, cli, room_io
from livekit.agents.llm import function_tool
from livekit.agents.voice import RunContext
from livekit.plugins import elevenlabs, lemonslice, mistralai

from utils import load_prompt

logger = logging.getLogger("lemonslice-salary-coach")
logger.setLevel(logging.INFO)

load_dotenv(".env.local")

DEFAULT_MISTRAL_MODEL = "mistral-medium-latest"
DEFAULT_ELEVEN_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"
DEFAULT_ELEVEN_STT_MODEL = "scribe_v2"
DEFAULT_ELEVEN_TTS_MODEL = "eleven_turbo_v2_5"
DEFAULT_LANGUAGE_CODE = "en"
ELEVEN_DEFAULT_VOICE_ID = os.getenv("ELEVEN_DEFAULT_VOICE_ID", DEFAULT_ELEVEN_VOICE_ID)

server = AgentServer()


def _extract_error_message(raw: bytes) -> str:
    if not raw:
        return "Unknown error"
    try:
        payload = json.loads(raw.decode("utf-8", errors="ignore"))
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str):
                return detail
            if isinstance(detail, dict):
                message = detail.get("message") or detail.get("detail")
                if isinstance(message, str):
                    return message
            message = payload.get("message")
            if isinstance(message, str):
                return message
    except json.JSONDecodeError:
        pass
    return raw.decode("utf-8", errors="ignore").strip()[:300]


def _http_json_request(url: str, *, headers: dict[str, str], timeout: float = 20.0) -> dict:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    if not body:
        return {}
    payload = json.loads(body.decode("utf-8"))
    if isinstance(payload, dict):
        return payload
    return {"data": payload}


def _build_silence_wav_bytes(duration_ms: int = 300, sample_rate: int = 16000) -> bytes:
    samples = int(sample_rate * duration_ms / 1000)
    pcm = b"\x00\x00" * samples
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


def _build_multipart_form(
    *,
    fields: dict[str, str],
    file_field: str,
    file_name: str,
    file_bytes: bytes,
    file_content_type: str,
) -> tuple[bytes, str]:
    boundary = f"----codex-boundary-{int(time.time() * 1000)}"
    chunks: list[bytes] = []

    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_name}"\r\n'.encode(
            "utf-8"
        )
    )
    chunks.append(f"Content-Type: {file_content_type}\r\n\r\n".encode("utf-8"))
    chunks.append(file_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))

    return b"".join(chunks), boundary


def _validate_required_provider_env() -> None:
    missing = [
        env_name
        for env_name in ("MISTRAL_API_KEY", "ELEVEN_API_KEY")
        if not os.getenv(env_name)
    ]
    if missing:
        missing_vars = ", ".join(missing)
        raise RuntimeError(
            f"Missing required environment variable(s): {missing_vars}. "
            "Set them in agent/.env.local before starting the backend."
        )


def _validate_mistral_model_access() -> None:
    try:
        payload = _http_json_request(
            "https://api.mistral.ai/v1/models",
            headers={"Authorization": f"Bearer {os.environ['MISTRAL_API_KEY']}"},
        )
    except urllib.error.HTTPError as error:
        detail = _extract_error_message(error.read())
        raise RuntimeError(f"Unable to validate Mistral model access: {detail}") from error
    except Exception as error:
        raise RuntimeError(f"Unable to validate Mistral model access: {error}") from error

    models = payload.get("data", [])
    model_ids = {
        item.get("id") for item in models if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if DEFAULT_MISTRAL_MODEL not in model_ids:
        sample = ", ".join(sorted(model_ids)[:10])
        raise RuntimeError(
            "Configured Mistral model is not available for this API key: "
            f"{DEFAULT_MISTRAL_MODEL}. Available sample: {sample}"
        )


def _validate_eleven_tts_model_access() -> None:
    request_data = json.dumps(
        {
            "text": "Model validation check",
            "model_id": DEFAULT_ELEVEN_TTS_MODEL,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_DEFAULT_VOICE_ID}",
        method="POST",
        data=request_data,
        headers={
            "xi-api-key": os.environ["ELEVEN_API_KEY"],
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20.0) as response:
            if response.status != 200:
                raise RuntimeError(f"Unexpected ElevenLabs TTS status code: {response.status}")
            response.read(1)
    except urllib.error.HTTPError as error:
        detail = _extract_error_message(error.read())
        raise RuntimeError(
            "Configured ElevenLabs TTS model/voice is not available for this API key: "
            f"model={DEFAULT_ELEVEN_TTS_MODEL}, voice_id={ELEVEN_DEFAULT_VOICE_ID}. Detail: {detail}"
        ) from error
    except Exception as error:
        raise RuntimeError(f"Unable to validate ElevenLabs TTS model access: {error}") from error


def _validate_eleven_stt_model_access() -> None:
    audio_bytes = _build_silence_wav_bytes()
    form_body, boundary = _build_multipart_form(
        fields={
            "model_id": DEFAULT_ELEVEN_STT_MODEL,
            "language_code": DEFAULT_LANGUAGE_CODE,
        },
        file_field="file",
        file_name="validation.wav",
        file_bytes=audio_bytes,
        file_content_type="audio/x-wav",
    )

    request = urllib.request.Request(
        "https://api.elevenlabs.io/v1/speech-to-text",
        method="POST",
        data=form_body,
        headers={
            "xi-api-key": os.environ["ELEVEN_API_KEY"],
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20.0) as response:
            if response.status != 200:
                raise RuntimeError(f"Unexpected ElevenLabs STT status code: {response.status}")
            response.read()
    except urllib.error.HTTPError as error:
        detail = _extract_error_message(error.read())
        raise RuntimeError(
            "Configured ElevenLabs STT model is not available for this API key: "
            f"model={DEFAULT_ELEVEN_STT_MODEL}. Detail: {detail}"
        ) from error
    except Exception as error:
        raise RuntimeError(f"Unable to validate ElevenLabs STT model access: {error}") from error


def _validate_provider_model_compatibility() -> None:
    _validate_mistral_model_access()
    _validate_eleven_tts_model_access()
    _validate_eleven_stt_model_access()


_validate_required_provider_env()
_validate_provider_model_compatibility()


@dataclass
class BossConfig:
    """Configuration for each boss type including voice and avatar settings."""

    voice_id: str
    avatar_image_url: str
    avatar_prompt: str


BOSS_CONFIGS = {
    "easy": BossConfig(
        voice_id=ELEVEN_DEFAULT_VOICE_ID,
        avatar_image_url=os.getenv("EASY_BOSS_IMAGE_URL", "https://iili.io/frL9tuj.png"),
        avatar_prompt="Be warm and encouraging in your movements. Use open gestures and smile naturally. Show genuine interest and supportiveness through body language.",
    ),
    "medium": BossConfig(
        voice_id=ELEVEN_DEFAULT_VOICE_ID,
        avatar_image_url=os.getenv("MEDIUM_BOSS_IMAGE_URL", "https://iili.io/frL9L8u.png"),
        avatar_prompt="Be professional and thoughtful in your movements. Use controlled gestures. Show engagement through body language.",
    ),
    "hard": BossConfig(
        voice_id=ELEVEN_DEFAULT_VOICE_ID,
        avatar_image_url=os.getenv("HARD_BOSS_IMAGE_URL", "https://iili.io/frL9Qyb.png"),
        avatar_prompt="Be direct and professional in your movements. Use controlled gestures. Show confidence through body language.",
    ),
}


@dataclass
class TurnLatency:
    """Per-turn latency checkpoints for diagnostics."""

    turn_id: int
    end_of_speech_ts: Optional[float] = None
    stt_final_ts: Optional[float] = None
    llm_start_ts: Optional[float] = None
    llm_first_token_ts: Optional[float] = None
    tts_start_ts: Optional[float] = None
    tts_first_audio_ts: Optional[float] = None
    avatar_speaking_ts: Optional[float] = None
    final_transcript: str = ""


@dataclass
class UserData:
    """Stores session state for the salary negotiation practice."""

    ctx: Optional[JobContext] = None
    boss_type: str = "easy"
    mode: str = "roleplay"
    session_start_time: float = 0.0
    roleplay_start_time: float = 0.0
    negotiation_phase: str = "intro"
    coaching_requests: int = 0
    conversation_highlights: list[str] = field(default_factory=list)
    timer_task: Optional[asyncio.Task] = None
    session_ended: bool = False
    turn_counter: int = 0
    active_turn_id: Optional[int] = None
    pending_llm_turn_ids: list[int] = field(default_factory=list)
    pending_tts_turn_ids: list[int] = field(default_factory=list)
    turn_latency: dict[int, TurnLatency] = field(default_factory=dict)

    def summarize(self) -> str:
        return f"Salary negotiation practice. Difficulty: {self.boss_type}. Mode: {self.mode}"


RunContext_T = RunContext[UserData]


class BaseBossAgent(Agent):
    """Base class for all boss agents with coaching functionality."""

    def __init__(self, instructions: str, tts: elevenlabs.TTS) -> None:
        super().__init__(
            instructions=instructions,
            tts=tts,
        )

    def _new_turn(self, userdata: UserData) -> int:
        userdata.turn_counter += 1
        turn_id = userdata.turn_counter
        userdata.active_turn_id = turn_id
        userdata.turn_latency[turn_id] = TurnLatency(turn_id=turn_id)
        return turn_id

    def _get_or_create_active_turn(self, userdata: UserData) -> int:
        if userdata.active_turn_id is not None:
            return userdata.active_turn_id
        return self._new_turn(userdata)

    @staticmethod
    def _delta_ms(base_ts: Optional[float], current_ts: Optional[float]) -> Optional[float]:
        if base_ts is None or current_ts is None:
            return None
        return round((current_ts - base_ts) * 1000, 1)

    def _log_turn_snapshot(self, userdata: UserData, turn_id: int, stage: str) -> None:
        timing = userdata.turn_latency.get(turn_id)
        if not timing:
            return

        eos = timing.end_of_speech_ts
        payload = {
            "turn_id": turn_id,
            "stage": stage,
            "timestamps": {
                "end_of_speech": timing.end_of_speech_ts,
                "stt_final": timing.stt_final_ts,
                "llm_start": timing.llm_start_ts,
                "llm_first_token": timing.llm_first_token_ts,
                "tts_start": timing.tts_start_ts,
                "tts_first_audio": timing.tts_first_audio_ts,
                "avatar_speaking": timing.avatar_speaking_ts,
            },
            "latency_ms_from_eos": {
                "stt_final": self._delta_ms(eos, timing.stt_final_ts),
                "llm_start": self._delta_ms(eos, timing.llm_start_ts),
                "llm_first_token": self._delta_ms(eos, timing.llm_first_token_ts),
                "tts_start": self._delta_ms(eos, timing.tts_start_ts),
                "tts_first_audio": self._delta_ms(eos, timing.tts_first_audio_ts),
                "avatar_speaking": self._delta_ms(eos, timing.avatar_speaking_ts),
            },
            "transcript": timing.final_transcript,
        }
        logger.info(f"TURN_TIMING {payload}")

    @staticmethod
    def _claim_pending_turn_id(queue: list[int], userdata: UserData, metric_name: str) -> Optional[int]:
        if queue:
            return queue.pop(0)

        fallback = [
            turn_id
            for turn_id, timing in userdata.turn_latency.items()
            if timing.stt_final_ts is not None and getattr(timing, metric_name) is None
        ]
        if fallback:
            return max(fallback)
        return None

    def _build_session_summary(self, userdata: UserData) -> dict:
        def delta_ms(a: Optional[float], b: Optional[float]) -> Optional[float]:
            if a is None or b is None:
                return None
            return round((b - a) * 1000, 1)

        sorted_turns = [userdata.turn_latency[k] for k in sorted(userdata.turn_latency.keys())]
        filtered_turns = [
            t for t in sorted_turns if t.end_of_speech_ts is not None or t.stt_final_ts is not None
        ]

        per_turn = []
        for t in filtered_turns:
            eos = t.end_of_speech_ts or t.stt_final_ts
            turn_entry = {
                "turn_id": t.turn_id,
                "transcript": t.final_transcript,
                "latency_ms_from_eos": {
                    "stt_final": delta_ms(eos, t.stt_final_ts),
                    "llm_start": delta_ms(eos, t.llm_start_ts),
                    "llm_first_token": delta_ms(eos, t.llm_first_token_ts),
                    "tts_start": delta_ms(eos, t.tts_start_ts),
                    "tts_first_audio": delta_ms(eos, t.tts_first_audio_ts),
                    "avatar_speaking": delta_ms(eos, t.avatar_speaking_ts),
                },
            }
            per_turn.append(turn_entry)

        metrics = [
            "stt_final",
            "llm_start",
            "llm_first_token",
            "tts_start",
            "tts_first_audio",
            "avatar_speaking",
        ]
        aggregate = {}
        for metric in metrics:
            values = [
                t["latency_ms_from_eos"][metric]
                for t in per_turn
                if t["latency_ms_from_eos"][metric] is not None
            ]
            if values:
                aggregate[metric] = {
                    "count": len(values),
                    "avg_ms": round(sum(values) / len(values), 1),
                    "min_ms": min(values),
                    "max_ms": max(values),
                }
            else:
                aggregate[metric] = {
                    "count": 0,
                    "avg_ms": None,
                    "min_ms": None,
                    "max_ms": None,
                }

        return {
            "turn_count": len(per_turn),
            "per_turn": per_turn,
            "aggregate": aggregate,
        }

    async def on_enter(self) -> None:
        """Called when the agent first starts."""
        agent_name = self.__class__.__name__
        logger.info(f"Starting {agent_name}")

        userdata: UserData = self.session.userdata
        if userdata.ctx and userdata.ctx.room:
            await userdata.ctx.room.local_participant.set_attributes({
                "agent": agent_name,
                "mode": userdata.mode,
            })

        userdata.mode = "roleplay"
        userdata.roleplay_start_time = time.time()

        if userdata.timer_task is None or userdata.timer_task.done():
            userdata.timer_task = asyncio.create_task(self._start_session_timer(userdata, 180))

        def on_user_state_changed(ev) -> None:
            if ev.new_state == "speaking":
                self._get_or_create_active_turn(userdata)
                return

            if ev.old_state == "speaking" and ev.new_state in {"listening", "away"}:
                turn_id = self._get_or_create_active_turn(userdata)
                timing = userdata.turn_latency[turn_id]
                if timing.end_of_speech_ts is None:
                    timing.end_of_speech_ts = getattr(ev, "created_at", time.time())
                    self._log_turn_snapshot(userdata, turn_id, "end_of_speech")

        def on_user_input_transcribed(ev) -> None:
            if not getattr(ev, "is_final", False):
                return

            transcript = (getattr(ev, "transcript", "") or "").strip()
            if not transcript:
                return

            turn_id = self._get_or_create_active_turn(userdata)
            timing = userdata.turn_latency[turn_id]
            event_ts = getattr(ev, "created_at", time.time())

            if timing.end_of_speech_ts is None:
                timing.end_of_speech_ts = event_ts
            if timing.stt_final_ts is None:
                timing.stt_final_ts = event_ts
            timing.final_transcript = transcript

            if turn_id not in userdata.pending_llm_turn_ids:
                userdata.pending_llm_turn_ids.append(turn_id)
            userdata.active_turn_id = None
            self._log_turn_snapshot(userdata, turn_id, "stt_final")

        def on_metrics_collected(ev) -> None:
            metrics = getattr(ev, "metrics", None)
            metric_type = getattr(metrics, "type", "")
            if metric_type == "llm_metrics":
                turn_id = self._claim_pending_turn_id(userdata.pending_llm_turn_ids, userdata, "llm_start_ts")
                if turn_id is None:
                    return

                timing = userdata.turn_latency.get(turn_id)
                if not timing or timing.llm_start_ts is not None:
                    return

                end_ts = float(getattr(metrics, "timestamp", time.time()))
                duration = float(getattr(metrics, "duration", 0.0))
                ttft = max(float(getattr(metrics, "ttft", 0.0)), 0.0)
                timing.llm_start_ts = end_ts - duration
                timing.llm_first_token_ts = timing.llm_start_ts + ttft

                if turn_id not in userdata.pending_tts_turn_ids:
                    userdata.pending_tts_turn_ids.append(turn_id)
                self._log_turn_snapshot(userdata, turn_id, "llm_first_token")
                return

            if metric_type == "tts_metrics":
                turn_id = self._claim_pending_turn_id(userdata.pending_tts_turn_ids, userdata, "tts_start_ts")
                if turn_id is None:
                    return

                timing = userdata.turn_latency.get(turn_id)
                if not timing or timing.tts_start_ts is not None:
                    return

                end_ts = float(getattr(metrics, "timestamp", time.time()))
                duration = float(getattr(metrics, "duration", 0.0))
                ttfb = max(float(getattr(metrics, "ttfb", 0.0)), 0.0)
                timing.tts_start_ts = end_ts - duration
                timing.tts_first_audio_ts = timing.tts_start_ts + ttfb
                self._log_turn_snapshot(userdata, turn_id, "tts_first_audio")

        def on_agent_state_changed(ev) -> None:
            if ev.new_state != "speaking":
                return

            candidates = [
                turn_id
                for turn_id, timing in userdata.turn_latency.items()
                if timing.tts_first_audio_ts is not None and timing.avatar_speaking_ts is None
            ]
            if not candidates:
                return

            turn_id = max(candidates)
            timing = userdata.turn_latency.get(turn_id)
            if timing and timing.avatar_speaking_ts is None:
                timing.avatar_speaking_ts = getattr(ev, "created_at", time.time())
                self._log_turn_snapshot(userdata, turn_id, "avatar_speaking")

        self.session.on("user_state_changed", on_user_state_changed)
        self.session.on("user_input_transcribed", on_user_input_transcribed)
        self.session.on("metrics_collected", on_metrics_collected)
        self.session.on("agent_state_changed", on_agent_state_changed)

    async def on_exit(self) -> None:
        """Called when the agent session ends (disconnect or completion)."""
        userdata: UserData = self.session.userdata

        if userdata.timer_task and not userdata.timer_task.done():
            userdata.timer_task.cancel()
            logger.info("Session timer cancelled on exit")

        session_duration = time.time() - userdata.session_start_time
        logger.info(
            f"Session ended - Boss: {userdata.boss_type}, "
            f"Duration: {session_duration:.1f}s, "
            f"Coaching requests: {userdata.coaching_requests}, "
            f"Phase: {userdata.negotiation_phase}"
        )
        logger.info(f"SESSION_LATENCY_SUMMARY {self._build_session_summary(userdata)}")

    @function_tool()
    async def how_am_i_doing(self, context: RunContext_T) -> str:
        """User is asking for coaching feedback on their negotiation performance."""
        userdata = context.userdata
        userdata.mode = "coaching"
        userdata.coaching_requests += 1

        logger.info(f"Entering coaching mode (request #{userdata.coaching_requests})")

        if userdata.ctx and userdata.ctx.room:
            await userdata.ctx.room.local_participant.set_attributes({"mode": "coaching"})

        await self.update_instructions(
            f"{self.instructions}\n\nIMPORTANT: You are now in COACHING MODE. Break character from the boss role completely and provide honest, specific feedback on their negotiation performance so far. Speak naturally using complete sentences and paragraphs. Do not use markdown, bullet points, headings, emojis, or symbols. After giving feedback, tell them you'll switch back to the boss role when they're ready, and then call the return_to_roleplay function to actually switch back to roleplay mode."
        )

        return "Switching to coaching mode to provide feedback."

    @function_tool()
    async def return_to_roleplay(self, context: RunContext_T) -> str:
        """Return from coaching mode back to the boss role-play."""
        userdata = context.userdata
        userdata.mode = "roleplay"

        logger.info("Returning to roleplay mode")

        if userdata.ctx and userdata.ctx.room:
            await userdata.ctx.room.local_participant.set_attributes({"mode": "roleplay"})

        await self.update_instructions(self.instructions)

        return "Returning to boss role-play mode."

    async def _start_session_timer(self, userdata: UserData, duration: int):
        """Timer that ends the session after specified duration."""
        try:
            await asyncio.sleep(duration)
            if not userdata.session_ended:
                userdata.session_ended = True
                logger.info("Session timer expired - ending session")

                await self.session.say("Our practice session time is up. I hope you have a great day.")

                await asyncio.sleep(2.0)

                if userdata.ctx:
                    userdata.ctx.shutdown("Session timer expired")
        except asyncio.CancelledError:
            logger.info("Session timer cancelled (user disconnected early)")
        except Exception as error:
            logger.error(f"Error in session timer: {error}")


class EasyBossAgent(BaseBossAgent):
    """The Encourager - supportive, friendly boss who can also coach."""

    def __init__(self) -> None:
        config = BOSS_CONFIGS["easy"]
        super().__init__(
            instructions=load_prompt("easy_boss_prompt.yaml"),
            tts=elevenlabs.TTS(
                voice_id=config.voice_id,
                model=DEFAULT_ELEVEN_TTS_MODEL,
                language=DEFAULT_LANGUAGE_CODE,
            ),
        )

    async def on_enter(self) -> None:
        """Called when entering the easy boss session."""
        await super().on_enter()
        self.session.generate_reply(
            instructions="Warmly greet the user as their supportive boss. Start the salary discussion meeting naturally. Keep it brief and welcoming."
        )


class MediumBossAgent(BaseBossAgent):
    """The Skeptic - fair but demanding boss who can also coach."""

    def __init__(self) -> None:
        config = BOSS_CONFIGS["medium"]
        super().__init__(
            instructions=load_prompt("medium_boss_prompt.yaml"),
            tts=elevenlabs.TTS(
                voice_id=config.voice_id,
                model=DEFAULT_ELEVEN_TTS_MODEL,
                language=DEFAULT_LANGUAGE_CODE,
            ),
        )

    async def on_enter(self) -> None:
        """Called when entering the medium boss session."""
        await super().on_enter()
        self.session.generate_reply(
            instructions="Greet the user professionally as their skeptical boss. Ask what this meeting is about in a business-like manner."
        )


class HardBossAgent(BaseBossAgent):
    """The Busy Executive - impatient, difficult boss who can also coach."""

    def __init__(self) -> None:
        config = BOSS_CONFIGS["hard"]
        super().__init__(
            instructions=load_prompt("hard_boss_prompt.yaml"),
            tts=elevenlabs.TTS(
                voice_id=config.voice_id,
                model=DEFAULT_ELEVEN_TTS_MODEL,
                language=DEFAULT_LANGUAGE_CODE,
            ),
        )

    async def on_enter(self) -> None:
        """Called when entering the hard boss session."""
        await super().on_enter()

        def log_agent_speech(text: str):
            logger.info(f"HARD BOSS LLM OUTPUT: '{text}'")

        self.session.on("agent_speech_committed", log_agent_speech)

        self.session.generate_reply(
            instructions="Greet the user dismissively as their impatient executive boss. Let them know you only have a few minutes. Use complete sentences."
        )


@server.rtc_session(agent_name="lemonslice-salary-coach")
async def entrypoint(ctx: JobContext):
    """Main entry point for the salary negotiation coach."""
    logger.info("Starting salary negotiation coach session")
    logger.info(
        "Pipeline models: "
        f"STT={DEFAULT_ELEVEN_STT_MODEL}, "
        f"LLM={DEFAULT_MISTRAL_MODEL}, "
        f"TTS={DEFAULT_ELEVEN_TTS_MODEL}, "
        f"LANG={DEFAULT_LANGUAGE_CODE}"
    )

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()

    boss_type = participant.attributes.get("boss_type", "easy")
    logger.info(f"Boss type selected: {boss_type}")

    if boss_type not in ["easy", "medium", "hard"]:
        logger.warning(f"Invalid boss type '{boss_type}', defaulting to 'easy'")
        boss_type = "easy"

    boss_config = BOSS_CONFIGS[boss_type]

    userdata = UserData(
        ctx=ctx,
        boss_type=boss_type,
        session_start_time=time.time(),
    )

    if boss_type == "easy":
        boss_agent = EasyBossAgent()
    elif boss_type == "medium":
        boss_agent = MediumBossAgent()
    else:
        boss_agent = HardBossAgent()

    session = AgentSession[UserData](
        stt=elevenlabs.STT(
            model_id=DEFAULT_ELEVEN_STT_MODEL,
            language_code=DEFAULT_LANGUAGE_CODE,
        ),
        llm=mistralai.LLM(model=DEFAULT_MISTRAL_MODEL),
        tts=elevenlabs.TTS(
            voice_id=boss_config.voice_id,
            model=DEFAULT_ELEVEN_TTS_MODEL,
            language=DEFAULT_LANGUAGE_CODE,
        ),
        resume_false_interruption=False,
        userdata=userdata,
    )

    avatar = lemonslice.AvatarSession(
        agent_image_url=boss_config.avatar_image_url,
        agent_prompt=boss_config.avatar_prompt,
    )
    await avatar.start(session, room=ctx.room)

    await session.start(
        agent=boss_agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            delete_room_on_close=True,
        ),
    )


if __name__ == "__main__":
    cli.run_app(server)
