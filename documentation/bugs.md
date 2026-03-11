# Bugs & Fixes

Bugs identified during development and how they were fixed.

---

## Template

When adding a new bug entry, use this format:

```markdown
### [Date] Bug: [Brief title]

**Symptom:** What was observed?

**Cause:** Root cause (if known).

**Fix:** What was changed to resolve it?

**Files affected:** List of files modified.
```

---

## Entries

### [2026-03-01] Bug: No STT / no conversation; session closes immediately

**Symptom:** Once the LiveKit room and LemonSlice agent start, user speaks but nothing comes back; session ends quickly. Console showed "Tried to add a track for a participant, that's not present" (separate client-side issue).

**Cause:** Shirley's **ElevenLabs voice ID** (`d3MFdIuCfbAIwiu7jC4a`) was incorrectly stored in `eleven_api_key`. The worker passed it to STT/TTS as the API key; Eleven Labs expects an [API key from the dashboard](https://elevenlabs.io/docs/eleven-api/quickstart) for auth and a separate `voice_id` for TTS. Using the voice ID as the API key caused `APIConnectionError` and session close.

**Fix:** Use the voice ID only for TTS: set `tts_voice_id: d3MFdIuCfbAIwiu7jC4a` for Shirley in `avatar_registry.yaml`. Do not set `eleven_api_key` for Shirley so the worker uses `ELEVEN_API_KEY` from env for authentication.

**Files affected:** `backend/avatar_registry.yaml`
