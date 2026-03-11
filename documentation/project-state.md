# Project State

Current state of the project as of the last update.

---

## Overview

**Project:** LemonSlice Salary Negotiation Coach (LiveKit example import)

**Location:** `experiments/lemonslice/`

**Purpose:** Practice salary negotiation with AI boss personas using LiveKit Agents and LemonSlice avatars.

---

## Architecture

- **Frontend:** `frontend/` — Next.js (App Router), web-only Instagram-style UI: fixed left sidebar (Feed, Chat, Search via Lucide), main content for Feed (center reel + right rail), Profile, Messages (two-panel: list | thread), Search; Inter font, Lucide icons, dark theme; reel nav via arrow keys and rail chevrons. “”.
- **Experiment:** `experiments/lemonslice/` — imported snapshot from `livekit-examples/python-agents-examples`
- **Agent runtime:** `experiments/lemonslice/agent/` — Python + LiveKit Agents + LemonSlice plugin
- **App runtime:** `frontend/` — main Reels app; `experiments/lemonslice/frontend/` — Next.js + Agents UI (alternate)
- **Integrations:** LiveKit APIs + LemonSlice avatars

---

## Key Files

| Path | Role |
|------|------|
| `frontend/` | Reels app: web UI, Feed/Profile/Message/Search views |
| `frontend/components/app/app.tsx` | AppContent (session, view state, LiveKit), web shell (sidebar + main), view routing |
| `frontend/components/app/left-sidebar.tsx` | Fixed left nav: Feed, Chat, Search (Lucide) |
| `frontend/components/app/feed-view.tsx` | Center reel + right rail (Like, Comment, Share, Call, chevrons); preview video when connecting |
| `frontend/components/app/profile-view.tsx` | Agent profile (web: avatar + stats, bio, Follow, Message, content grid with placeholders/images) |
| `frontend/components/app/message-view.tsx` | Two-panel: list (tabs, search) | thread (header, Video call only, real chat bubbles, input → POST /api/chat) |
| `frontend/app/api/chat/route.ts` | Proxy to backend POST /chat for text chat with avatar |
| `frontend/components/app/search-view.tsx` | Search agents (Lucide Search icon) |
| `experiments/lemonslice/README.md` | Imported project overview and setup |
| `experiments/lemonslice/agent/lemonslice-agent.py` | Main LiveKit agent with boss personalities + coaching mode |
| `experiments/lemonslice/agent/prompts/*.yaml` | Prompt definitions for Easy/Medium/Hard boss behavior |
| `experiments/lemonslice/frontend/app/page.tsx` | Main Next.js UI entrypoint |
| `experiments/lemonslice/frontend/package.json` | Frontend dependencies and scripts |

---

## Known Limitations

- Imported as a snapshot of the upstream `main` branch path only (no history tracking in this repo).

---

## Reels app: performance and UX notes

- **Connect time (4–6s):** Dominated by LiveKit room join, agent dispatch, and LemonSlice avatar start. Keep the agent worker running (warm) to avoid cold start; using LiveKit Cloud can reduce regional latency.
- **Response delay:** Reduced by lowering `min_endpointing_delay` (0.3s) and `max_endpointing_delay` (1.5s) in `AgentSession` so turn detection is snappier. Further gains need faster STT/LLM/TTS or streaming.
- **Idle “swipe” hint:** Only fires after 7s with no user or agent activity; reset on any transcript (including partial) and when the agent is speaking.
- **Next/Prev avatar (Option B):** One room per session. When the user switches avatar while connected, the frontend does **not** disconnect. It (1) publishes a data message `reels.switch_avatar` so the current agent shuts down, (2) calls `POST /dispatch-agent` so the backend dispatches a new agent to the **same** room with the new `avatar_id`. The user stays in the room; the new agent joins and provides the new avatar (prompt + LemonSlice). No 5–6 s reconnect. First connection is unchanged (token + RoomAgentDispatch). Agent worker resolves avatar from job metadata (dispatch) or participant attributes (first join), listens for `reels.switch_avatar` / `reels.agent_leave` on topic `reels.events`, and sets `delete_room_on_close=False` so the room persists when the agent leaves.
- **Avatar video (lag/fuzzy):** LemonSlice outputs 368×560 @ ~20fps. Quality is limited by network and source resolution; avoid upscaling the video element; use a stable connection.

---

## Prompts and avatar configuration (Reels)

- **Where it lives:** `backend/avatar_registry.yaml`. Each avatar has its own `system_prompt`, `avatar_motion_prompt`, and LemonSlice ref; prompts are **not** shared between avatars.
- **Per-avatar (registry):**
  - **Personality / what they say:** `system_prompt` — used as the LLM system instructions for that avatar only.
  - **Look and motion:** `lemonslice` (either `image_url` or `agent_id`) and `avatar_motion_prompt` (hints for LemonSlice). With `agent_id` the avatar is fully driven by LemonSlice (no image URL is sent to LiveKit or LemonSlice); with `image_url` the image URL is sent to LemonSlice for rendering. Only `lemonslice` is used by the backend/LemonSlice—never `preview_image_url`.
  - **Preview image (optional, UI only):** `preview_image_url` — used only by the frontend for feed/profile/message thumbnails before or outside a call. Not sent to LiveKit or LemonSlice. When using `lemonslice.type: agent_id` you typically omit it; the UI shows a placeholder (e.g. first letter of display name).
  - **Voice (optional):** `tts_voice_id` — ElevenLabs voice ID for this avatar. If omitted, the backend uses `ELEVEN_TTS_VOICE_ID` from env (one voice for all).
  - **Eleven Labs API key (optional):** `eleven_api_key` — ElevenLabs API key for this avatar. If omitted, the worker uses `ELEVEN_API_KEY` from env. Use when each avatar has its own Eleven Labs project/key.
  - **Caption (optional):** `caption` — Short feed caption (e.g. "Beauty Advice"). Exposed in the `/avatars` API; frontend feed uses it when present, otherwise falls back to display_name.
  - **Preview video (optional):** `preview_video_url` — URL to a short looping clip (e.g. MP4/WebM) shown in the feed while the new agent is connecting (instead of a static image). If unset, the feed uses `preview_image_url` if set, otherwise a placeholder.
  - **Profile images (optional):** `profile_image_urls` — list of image URLs shown in the profile content grid (in order). Upload images to `frontend/public/profile/<avatar_id>/` (e.g. `1.jpg`, `2.jpg`) or a CDN, then add the public URLs to `backend/avatar_registry.yaml` under `profile_image_urls`. The profile grid displays these in order; empty slots show placeholders.
- **Global (env):** STT/TTS models, Mistral model, default `ELEVEN_TTS_VOICE_ID`. See `backend/.env.local` and `reels_backend/config.py`.
- **Prompt leakage:** Each time an avatar is used (first connect or after switch), the worker creates a **new** agent instance with **that** avatar’s `system_prompt` only. The new agent gets a new session; conversation history is not shared between avatars. If you ever see one avatar “knowing” something only another was told, it would be a bug (e.g. room-level state); current design is one prompt per avatar, no sharing.
- **“I don’t have mic access”:** The LLM was sometimes saying that despite being in a voice call. The registry prompts now start with an explicit line: “You are in a live voice call; you hear the user’s voice. Never say you don’t have microphone access or that you can’t hear them.”

- **Text chat (Messages):** `POST /chat` (body: `avatar_id`, `message`, optional `thread_id`) uses the same avatar `system_prompt` and Mistral model as the voice agent. Conversation history is kept in memory per thread; not persisted. Frontend Message view sends to `/api/chat` and displays user/assistant bubbles; same personality as in voice.

---

## Environment

Required env vars (see `experiments/lemonslice/agent/.env.example` and `experiments/lemonslice/frontend/.env.example`):

- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `LIVEKIT_URL`
- `LEMONSLICE_API_KEY`
