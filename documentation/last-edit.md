# Last Edit

Summary of the most recent interaction.

---

## [2026-03-01] STT fix: voice ID vs API key (Shirley)

**What was done:**
- **Root cause:** Shirley's ElevenLabs **voice ID** (`d3MFdIuCfbAIwiu7jC4a`) had been stored in `eleven_api_key`. Per [ElevenLabs docs](https://elevenlabs.io/docs/eleven-api/quickstart), the API key is for authentication (from dashboard / env); voice_id is for TTS. Passing the voice ID as the API key caused STT `APIConnectionError` and session close.
- **Fix:** Set `tts_voice_id: d3MFdIuCfbAIwiu7jC4a` for Shirley; do not set `eleven_api_key` so worker uses `ELEVEN_API_KEY` from env. API key stays from env; only voice selection is per-avatar.

**Files changed:** `backend/avatar_registry.yaml`, `documentation/bugs.md`, `documentation/last-edit.md`

---

## [2026-03-01] Shirley integration: own agent ID, prompt, Eleven Labs key, caption

**What was done:**
- **Registry:** Added optional `eleven_api_key` and `caption` to `AvatarEntry`; `PublicAvatar` and `/avatars` API now expose `caption`.
- **Worker:** STT and TTS use `avatar.eleven_api_key or settings.eleven_api_key` so each avatar can have its own Eleven Labs key.
- **Avatar registry:** Replaced the three placeholder avatars (easy/medium/hard) with a single Shirley entry: `avatar_id: shirley`, LemonSlice `agent_id: agent_b1c0f1faf5938acc`, full beauty-advisor system prompt, `caption: Beauty Advice`, per-avatar `eleven_api_key`, `avatar_motion_prompt` for calm/professional delivery.
- **Frontend:** `AvatarItem` has optional `caption`; feed uses `avatar.caption ?? display_name fallback` (removed hardcoded `MOCK_CAPTIONS`).
- **Tests:** Added `test_get_avatars_returns_caption_when_present`; existing tests updated for optional fields. Documented per-avatar Eleven Labs key and caption in project-state.

**Files changed:**
- `backend/reels_backend/registry.py` (eleven_api_key, caption on AvatarEntry and PublicAvatar)
- `backend/reels_backend/api.py` (caption on AvatarPublicResponse and get_avatars)
- `backend/reels_backend/agent_worker.py` (per-avatar eleven_api_key for STT/TTS)
- `backend/avatar_registry.yaml` (Shirley only: agent_id, prompt, caption, eleven_api_key)
- `frontend/lib/types.ts` (caption on AvatarItem)
- `frontend/components/app/feed-view.tsx` (use API caption, remove MOCK_CAPTIONS)
- `backend/tests/test_api.py` (caption test)
- `documentation/project-state.md`, `documentation/last-edit.md`

---

## [2026-03-01] Agent switch, status, repost, messages, profile, real chat

**What was done:**
- **Hide status:** Removed connection/switch status text from the feed UI. FeedView no longer receives or renders `status`; only errors (e.g. mic denied, switch failed) are shown.
- **Remove repost:** Removed the Repost (Repeat2) button and count from the feed right rail. Kept Like, Comment, Share, Call.
- **Messages: video only:** Removed the Phone (audio call) icon from the message thread header; only the Video call button remains for starting a call.
- **Still video:** Added optional `preview_video_url` to backend registry and API; frontend `AvatarItem` and feed view show a looping `<video>` when the avatar has `preview_video_url` and there is no live track (connecting). Otherwise the static preview image is used. Documented in project-state.
- **Agent switch:** `reels.switch_avatar` is now emitted at the start of `switchAvatar` (when connected), before updating index or calling `connectToAvatarId`, so the old agent gets the shutdown signal immediately.
- **Profile placeholders:** Added a 3×3 content grid below the profile header with placeholder slots (Lucide Image icon). Optional `profile_image_urls` on registry/API and frontend types; grid shows real images where URLs exist. Documented where to upload and how to set URLs in project-state.
- **Real text chat:** Backend `POST /chat` (avatar_id, message, optional thread_id) uses the avatar’s `system_prompt` and same Mistral model as the agent; in-memory conversation history per thread; returns `{ reply }`. Frontend `POST /api/chat` proxy; MessageView uses real thread state, send on Enter or Send button, loading state, appends user + assistant messages.

**Files changed:**
- `frontend/components/app/app.tsx` (status not passed to FeedView; switchAvatar emits reels.switch_avatar first)
- `frontend/components/app/feed-view.tsx` (no status prop/block; no Repost; preview video when preview_video_url set)
- `frontend/components/app/message-view.tsx` (no Phone button; real thread state, input, sendMessage → /api/chat)
- `frontend/components/app/profile-view.tsx` (content grid with placeholders + optional profile_image_urls)
- `frontend/lib/types.ts` (preview_video_url, profile_image_urls on AvatarItem)
- `backend/reels_backend/registry.py` (preview_video_url, profile_image_urls; PublicAvatar)
- `backend/reels_backend/api.py` (AvatarPublicResponse fields; POST /chat, Mistral, _chat_history)
- `backend/pyproject.toml` (mistralai dependency)
- `frontend/app/api/chat/route.ts` (new proxy to backend /chat)
- `documentation/project-state.md` (preview video, profile images, docs)

---

## [2026-03-01] Web-only Instagram-style UI

**What was done:**
- **Removed phone-only UI:** No viewport detection, landing page, phone frame, or bottom bar. App is always a full web layout.
- **Web shell:** Fixed left sidebar (72px) with Lucide icons: Feed (Home), Chat (MessageCircle), Search. Main content area (flex 1) shows Feed, Profile, Message, or Search.
- **Feed:** Center reel (9:16, max-height) + right rail with Lucide actions: ChevronUp/Down, Heart, MessageCircle, Repeat2, Send, Phone (Call). Bottom-left overlay: profile, username, Follow, caption.
- **Messages:** Two-panel layout. Left: tabs (Primary/General/Requests), search, conversation list with unread dots. Right: thread header (avatar, name, View profile, Phone, Video, Info), message bubbles, input bar (Smile, input, ImagePlus, Mic, Send). Empty state when no thread selected. All icons Lucide.
- **Profile:** Web layout: large avatar + meta (name, stats, bio, Follow, Message) in a row; max-width 900px, centered. Lucide User for empty state.
- **Search:** Search input with Lucide Search icon; filtered list; max-width 600px, centered.
- **Deps:** lucide-react, Inter via next/font/google, optimizePackageImports in next.config. Dark theme: --bg #0a0a0a, --panel #121212, --panel-border #262626.
- **Deleted:** landing-page.tsx, phone-frame.tsx, bottom-bar.tsx. **New:** left-sidebar.tsx.

**Files changed:**
- `frontend/package.json` (lucide-react), `frontend/next.config.ts` (optimizePackageImports), `frontend/app/layout.tsx` (Inter font)
- `frontend/components/app/app.tsx` (remove phone/landing/PhoneFrame; web shell with LeftSidebar + app-main)
- `frontend/components/app/left-sidebar.tsx` (new), `frontend/components/app/feed-view.tsx` (center + rail, Lucide), `frontend/components/app/message-view.tsx` (two-panel, Lucide), `frontend/components/app/profile-view.tsx` (web layout, Lucide), `frontend/components/app/search-view.tsx` (Lucide Search)
- `frontend/app/globals.css` (remove landing/phone/bottom-bar; add app-shell, app-sidebar, app-main; feed--web, message--web, profile--web, search--web; dark palette)
- Deleted: `landing-page.tsx`, `phone-frame.tsx`, `bottom-bar.tsx`

---

## [2026-03-01] Instagram-style phone-only frontend

**What was done:**
- **Viewport:** Desktop (width > 500px) shows a landing page only (“Open on your phone to continue”); phone-sized viewport shows the app inside a fixed phone frame (390×844).
- **Views:** Feed (full-screen reels with profile/caption overlay, right rail: Like, Comment, Repost, Share, Call), Profile (mock posts/followers/following, bio, Follow, Message), Message (chat list per avatar, thread with mock history, Call/Video call that switch to Feed and connect), Search (filter avatars by name).
- **Bottom bar:** Feed, Chat, Search only (no Home, Profile, or Plus). SVG icons for tabs.
- **Navigation:** Reel navigation via ArrowUp/ArrowDown only (no touch swipe). Tab switching via bottom bar. Call from Message view switches to Feed and starts LiveKit session.
- **New components:** `LandingPage`, `PhoneFrame`, `BottomBar`, `FeedView`, `ProfileView`, `MessageView`, `SearchView` under `frontend/components/app/`. Session/token/avatar logic remains in `AppContent` in `app.tsx`; LiveKit video attaches to Feed stage when on Feed.

**Files changed:**
- `frontend/components/app/app.tsx` (viewport detection, AppContent with view state, Feed/Profile/Message/Search + BottomBar)
- `frontend/components/app/landing-page.tsx` (new)
- `frontend/components/app/phone-frame.tsx` (new)
- `frontend/components/app/bottom-bar.tsx` (new)
- `frontend/components/app/feed-view.tsx` (new)
- `frontend/components/app/profile-view.tsx` (new)
- `frontend/components/app/message-view.tsx` (new)
- `frontend/components/app/search-view.tsx` (new)
- `frontend/app/globals.css` (landing, phone frame, app-content, bottom bar, feed/profile/message/search view styles)

---

## [2026-02-28] Prompts: mic-access fix, per-avatar voice, docs

**What was done:**
- **“I don’t have mic access”:** Added an explicit first line to every avatar `system_prompt` in `avatar_registry.yaml`: “You are in a live voice call; you hear the user's voice. Never say you don't have microphone access or that you can't hear them.”
- **Per-avatar voice:** Added optional `tts_voice_id` to `AvatarEntry` in registry; agent worker uses `avatar.tts_voice_id or settings.eleven_tts_voice_id` for TTS so each avatar can have a distinct voice (optional in YAML; default remains env).
- **Docs:** New “Prompts and avatar configuration (Reels)” section in `project-state.md`: where prompts/voice/appearance live (registry vs env), that prompts are not shared between avatars (no leakage by design), LemonSlice dashboard only relevant when using `agent_id`, and note on the mic-access prompt fix.

**Files changed:**
- `backend/avatar_registry.yaml` (mic line in all three prompts)
- `backend/reels_backend/registry.py` (optional `tts_voice_id`)
- `backend/reels_backend/agent_worker.py` (TTS uses per-avatar voice_id when set)
- `documentation/project-state.md` (prompts and avatar config section)

---

## [2026-02-28] STARTUP.md: browser-only workflow (no curl)

**What was done:**
- Simplified `documentation/STARTUP.md`: removed all curl examples and “Backend API (no browser)” testing. Doc now focuses on starting the three processes (Backend API, Agent worker, Frontend) and using the app at http://localhost:3000 in the browser (mic, talk, Next/Prev). Optional: open http://127.0.0.1:8000/health in browser to confirm backend.

**Files changed:**
- `documentation/STARTUP.md`

---

## [2026-02-28] Option B: one room, dispatch new agent on avatar switch

**What was done:**
- **Backend:** New `POST /dispatch-agent` (body: `room_name`, `avatar_id`) validates avatar and calls LiveKit Agent Dispatch API to dispatch the same agent to the existing room with `metadata: {"avatar_id"}`. Frontend proxy at `POST /api/dispatch-agent`.
- **Agent worker:** Resolves avatar from `ctx.job.metadata` (dispatch) first, else participant attributes (first join). Listens for `data_received` on room; on `reels.switch_avatar` or `reels.agent_leave` calls `session.shutdown()`. `delete_room_on_close=False` so room persists when agent leaves.
- **Frontend:** When already connected and user switches avatar, no longer calls `session.end()`. Publishes data message `reels.switch_avatar` to topic `reels.events`, then calls `/api/dispatch-agent` with current room name and new avatar_id. Stores `roomNameRef` on connect for dispatch. First connection unchanged (token + session.start()).
- **Docs:** Updated `documentation/project-state.md` with Option B flow. **Tests:** Added tests for dispatch-agent (404 unknown avatar, 400/422 invalid payload, 204 success with mocked LiveKit API).

**Files changed:**
- `backend/reels_backend/api.py` (DispatchAgentRequest, POST /dispatch-agent, livekit_api)
- `backend/reels_backend/agent_worker.py` (job metadata, data_received handler, delete_room_on_close=False)
- `frontend/app/api/dispatch-agent/route.ts` (new proxy)
- `frontend/components/app/app.tsx` (roomNameRef, connectToAvatarId Option B path, connectCurrentAvatar delegates when connected)
- `documentation/project-state.md`, `backend/tests/test_api.py`

---

## [2026-02-28] Reels: Next/Prev room switch fix + remove 7s idle timer

**What was done:**
- **Next/Prev actually switching room:** Buttons were only updating the label (easy/medium/hard); the LiveKit room stayed the same. Token for the new avatar is now chosen at request time: **tokenSource** uses `requestedAvatarIdRef.current ?? selectedAvatarId ?? activeAvatar?.avatar_id` so when we reconnect after `connectToAvatarId(avatarId)`, the session’s token request uses the ref (already set to the new avatar) and joins the correct room.
- **7s idle timer removed:** Backend no longer creates IdleSignalScheduler or any idle/activity events. Frontend no longer shows idle hint (handler left as no-op for future use). Idle can be re-added with a new design later.

**Files changed:**
- `frontend/components/app/app.tsx` (tokenSource uses requestedAvatarIdRef; onDataReceived no longer sets idle hint; debug instrumentation removed)
- `backend/reels_backend/agent_worker.py` (idle scheduler, handlers, and UserData.idle_scheduler removed; IdleSignalScheduler import removed)

---

## [2026-02-28] Reels UX fixes: idle hint, next-avatar buttons, response delay, docs

**What was done:**
- **7s idle hint while talking:** Idle timer now resets on any transcript (including non-final) and when agent state is "speaking", so the swipe hint does not show every 7s during conversation.
- **Next/Prev avatar buttons:** Reconnect effect now depends on `session.isConnected` so after ending the session to switch avatar, the effect re-runs and starts the new session.
- **Response delay:** Set `min_endpointing_delay=0.3` and `max_endpointing_delay=1.5` on `AgentSession` for snappier turn detection.
- **Docs:** Added Reels performance/UX notes to `documentation/project-state.md` (connect time, response delay, idle, next-avatar, avatar video quality).

**Files changed:**
- `backend/reels_backend/agent_worker.py` (idle resets, endpointing delays)
- `frontend/components/app/app.tsx` (effect deps)
- `documentation/project-state.md`, `documentation/last-edit.md`

---

## [2026-02-28] Replaced experiment with lemonslice import

**What was done:**
- Removed the previous experiment content under `experiments/elevenlabs_agent_demo/`
- Created `experiments/lemonslice/`
- Imported only `complex-agents/avatars/lemonslice` from `https://github.com/livekit-examples/python-agents-examples` using sparse checkout in a temporary directory
- Confirmed old experiment path no longer exists
- Updated project docs to reflect LemonSlice/LiveKit experiment details

**Files changed:**
- `experiments/elevenlabs_agent_demo/**` (removed)
- `experiments/lemonslice/**` (added from upstream path snapshot)
- `documentation/project-state.md`
- `documentation/last-edit.md`

---

## [2025-02-28] Frontend folder structure

**What was done:**
- Created `frontend/` directory with full folder structure for a vertical-slice architecture
- `public/` — favicon only (kept tiny)
- `src/routes/` — screens/routes
- `src/features/` — auth, feed, profile, call, payments, settings
- `src/components/` — shared UI
- `src/services/` — api, realtime, media
- `src/state/` — app state
- `src/styles/` — global styles + tokens
- `src/utils/` — pure helpers
- `src/types/` — shared TypeScript shapes
- `src/validations/` — runtime validation
- Added `.gitkeep` in empty dirs; copied favicon from elevenlabs demo

**Files created:**
- `frontend/` tree (directories + .gitkeep)
- `frontend/public/favicon.ico`

---

## [2025-02-28] Initial documentation setup

**What was done:**
- Created `documentation/` folder
- Added `README.md` (overview and index)
- Added `challenges.md` (challenges and solutions)
- Added `bugs.md` (bugs and fixes)
- Added `project-state.md` (current project state)
- Added `last-edit.md` (this file)
- Created Cursor rule to instruct the agent to update these docs after every interaction

**Files created:**
- `documentation/README.md`
- `documentation/challenges.md`
- `documentation/bugs.md`
- `documentation/project-state.md`
- `documentation/last-edit.md`
- `.cursor/rules/documentation-update.mdc`
