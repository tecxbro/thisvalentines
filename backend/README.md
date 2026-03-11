# Valentines Reels Backend (v1)

Standalone backend for a reels-style LiveKit avatar feed:

- `GET /avatars` returns feed metadata.
- `POST /token { avatar_id }` creates a fresh LiveKit room/token (Option A swipe semantics).
- LiveKit agent worker resolves avatar persona from registry and runs ElevenLabs STT/TTS + Mistral LLM + LemonSlice avatar stream.
- Worker emits `reels.idle_suggest_next` after 7 seconds of user silence.
- Silero VAD is enabled so ElevenLabs STT can operate in the streaming voice pipeline.

## Directory layout

```text
backend/
├── avatar_registry.yaml
├── reels_backend/
│   ├── api.py
│   ├── agent_worker.py
│   ├── config.py
│   ├── idle.py
│   ├── registry.py
│   └── token_service.py
└── tests/
```

## Environment

1. Copy `backend/.env.example` to `backend/.env.local`.
2. Fill in LiveKit, LemonSlice, Mistral, and ElevenLabs keys.

## Install

```bash
cd backend
uv sync --group dev
```

## Run API

```bash
cd backend
uv run uvicorn reels_backend.api:app --host 0.0.0.0 --port 8000 --reload
```

Routes:

- `GET /health`
- `GET /avatars`
- `POST /token`
- `POST /dispatch-agent`
- `POST /chat`
- `GET /demo` (minimal reel-style test UI)

`POST /token` request body:

```json
{ "avatar_id": "easy" }
```

## Run agent worker

```bash
cd backend
uv run python -m reels_backend.agent_worker dev
```

The worker listens for LiveKit dispatch using `AGENT_NAME` and binds avatar behavior from participant attribute `avatar_id`.

## Local smoke test checklist

1. Start API.
2. Start agent worker.
3. Open `http://localhost:8000/demo` and click **Join & Talk**.
4. Select next/prev reels and verify reconnect behavior.
5. Speak and verify STT -> LLM -> TTS -> LemonSlice avatar output.
6. Stay silent for 7 seconds and verify in-app idle hint and/or data event.
7. Optional direct API check:

```bash
curl -X POST http://localhost:8000/token \
  -H "content-type: application/json" \
  -d '{"avatar_id":"easy"}'
```

8. Optional data event payload:

```json
{
  "type": "reels.idle_suggest_next",
  "avatar_id": "easy",
  "idle_seconds": 7
}
```
