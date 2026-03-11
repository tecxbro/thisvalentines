# How to start the Reels app (backend + frontend + agent)

You need **three processes** running. You do **not** "start" `/health` — it is just a URL you can open to check that the backend API is up.

## 1. Backend API (port 8000)

One process. It serves all of: `/health`, `/avatars`, `/token`, `/demo`.

```bash
cd backend
uv run uvicorn reels_backend.api:app --host 0.0.0.0 --port 8000 --reload
```

- **Check it’s running:** open [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) in a browser. You should see `{"status":"ok","avatars_loaded":3}` (or similar).

## 2. Agent worker (separate process)

Another process. It connects to LiveKit and runs the avatar (STT → LLM → TTS → LemonSlice). If this is not running, the frontend will get a token but no agent will join the room (no avatar, no voice).

```bash
cd backend
uv run python -m reels_backend.agent_worker dev
```

Leave it running in its own terminal.

## 3. Frontend (port 3000)

```bash
cd frontend
pnpm dev
```

(or `npm run dev`). Next.js will serve the app at [http://localhost:3000](http://localhost:3000).

---

## Order and restarting

- Start all three; order does not matter, but **all must be running** when you use the app.
- To restart: stop the process (e.g. Ctrl+C in its terminal), then run the same command again. You do not “start 8000/health” — you start the **API server** (step 1), and use `/health` only to **check** that it’s up.
- Use the app at **http://localhost:3000** (the main frontend). Do not use the experiments/lemonslice frontend if you want to test the reels backend + our fixes.

## Summary: what to run

| What         | Where to run it | What you see |
|--------------|-----------------|--------------|
| Backend API  | Terminal 1: `cd backend` then `uv run uvicorn reels_backend.api:app --host 0.0.0.0 --port 8000 --reload` | Server logs; leave running. |
| Agent worker | Terminal 2: `cd backend` then `uv run python -m reels_backend.agent_worker dev` | Agent logs; leave running. |
| Frontend     | Terminal 3: `cd frontend` then `pnpm dev` | “Ready” and localhost:3000; leave running. |

Then open **http://localhost:3000** in your browser, allow the microphone when asked, and use the app (talk to the avatar, use Next/Prev to switch). You don’t need to open or “start” the `/health` URL — that’s just a page you can open in a browser to confirm the backend is up (e.g. http://127.0.0.1:8000/health).
