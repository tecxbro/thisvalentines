# Swiggy Realtime Agent Instructions

## Config

- LemonSlice Hosted agent ID: `agent_e3cbf56e895e9c82`
- The app-local env file is [`.env.local`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/.env.local)
- Shared backend secrets still load from [`/Users/darshan/Documents/thisvalentines/backend/.env.local`](/Users/darshan/Documents/thisvalentines/backend/.env.local)

## Start The Servers

Run all commands from [`/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent).

### 1. Shared backend

```bash
../../../backend/.venv/bin/python -m uvicorn backend.server:app --reload --host 0.0.0.0 --port 3000
```

- Serves the Hosted LemonSlice room API and the Swiggy sidecar
- URL: `http://localhost:3000`

### 2. Main app

```bash
pnpm exec vite --host 0.0.0.0 --port 5173
```

- Main Hosted LemonSlice + Swiggy experience
- URL: `http://localhost:5173`

### 3. Swiggy text debug app

```bash
pnpm exec vite --host 0.0.0.0 --port 5174
```

- Text-only Swiggy sidecar tester
- URL: `http://localhost:5174/?debug=swiggy`

## Notes

- The backend is shared by both frontends.
- The debug page is fully live. Explicit confirmations can place real Swiggy orders or bookings on the authenticated account.
- The main app still uses LemonSlice Hosted and Daily.

## Terminal-Only Swiggy Validation

Use this when you want to test the current Swiggy sidecar directly from your terminal without LemonSlice or the browser UI.

### Terminal 1. Run the backend in the foreground

```bash
cd /Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent
../../../backend/.venv/bin/python -m uvicorn backend.server:app --reload --host 0.0.0.0 --port 3000
```

- Leave this terminal open.
- This shows request logs and any Python tracebacks.
- Rich tool traces do not appear in stdout. They come back in the JSON response body from the debug endpoint.

### Terminal 2. Send transcripts with curl

Reuse the same `session_id` across turns so the sidecar keeps its current flow state.

```bash
export SWIGGY_SESSION=swiggy-cli-test-1
curl -sS -X POST http://127.0.0.1:3000/swiggy/debug-transcript \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SWIGGY_SESSION\",\"transcription\":\"how are you\",\"event_type\":\"user_transcription\"}"
```

If `jq` is installed, you can pretty-print the response:

```bash
curl -sS -X POST http://127.0.0.1:3000/swiggy/debug-transcript \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SWIGGY_SESSION\",\"transcription\":\"show me grocery options for milk\",\"event_type\":\"user_transcription\"}" | jq
```

### What to inspect in the response

- `debug_trace.gate`
- `debug_trace.handled_by_sidecar`
- `debug_trace.planner_steps[*].tool_name`
- `debug_trace.planner_steps[*].arguments`
- `debug_trace.planner_steps[*].tool_result_text`
- `debug_trace.final_outcome`

### Recommended safe prompts

Start with:

- `how are you`
- `show me grocery options for milk`
- `find dineout options in Mumbai for 2 tonight`
- `order biryani from Biryani Blues`

Follow up with the same `SWIGGY_SESSION` if the flow stays open:

- `home address`
- `second one`
- `show me the menu`
- `show more`

### Important current behavior

- Pure prompts like `show my saved addresses` may currently gate out as `non_commerce` unless a Swiggy flow is already open.
- The current code only blocks final `place_food_order`, `checkout`, and `book_table` without explicit confirmation.
- Non-final write actions such as cart updates may still be reachable if the sidecar chooses them.
- If you want to avoid mutation risk, do not send explicit confirmation phrases like `yes`, `confirm`, `go ahead`, `place it`, `book it`, `checkout`, or `do it`.
