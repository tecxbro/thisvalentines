# Swiggy File Structure

This map covers the app-owned Swiggy surface only. It excludes `venv`, `node_modules`, `dist`, caches, and secrets.

## Top Level

```text
apps/swiggy-integration/
├── instructions.py
├── run.sh
├── swiggy_mcp_client.py
├── swiggy_mcp.py
├── swiggy_agent_one.py
├── swiggy_agent_two.py
├── swiggy_agent_phone.py
├── README.md
└── realtime-agent/
```

## Shared Swiggy Integration Layer

- [`instructions.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/instructions.py)
  - Shared Swiggy commerce prompt used by both the legacy runtime and the hosted backend sidecar.
- [`swiggy_mcp_client.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/swiggy_mcp_client.py)
  - Runtime-agnostic Swiggy MCP client.
  - Owns OAuth login, token storage, connection lifecycle, tool discovery, and direct tool execution across Food, Instamart, and Dineout.
- [`swiggy_mcp.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/swiggy_mcp.py)
  - Legacy VideoSDK adapter that exposes the shared MCP client as mounted agent tools.
- [`run.sh`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/run.sh)
  - Interactive setup and launch script for the legacy runtime.

## Legacy Runtime Entrypoints

- [`swiggy_agent_one.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/swiggy_agent_one.py)
  - Legacy multi-provider voice pipeline: Deepgram STT + Google LLM + Cartesia TTS.
- [`swiggy_agent_two.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/swiggy_agent_two.py)
  - Legacy lower-latency runtime using Gemini native audio.
- [`swiggy_agent_phone.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/swiggy_agent_phone.py)
  - Legacy phone-oriented runtime that registers the same Swiggy agent for telephony flows.

## Hosted Runtime

```text
apps/swiggy-integration/realtime-agent/
├── backend/
│   ├── __init__.py
│   ├── mistral_client.py
│   ├── orchestrator.py
│   ├── server.py
│   └── tests/test_orchestrator.py
├── src/
│   ├── api.js
│   ├── App.jsx
│   ├── index.jsx
│   ├── index.css
│   ├── providers/AgentStateProvider.tsx
│   └── components/
│       ├── AgentCall.jsx
│       ├── AgentVideoTile.jsx
│       ├── Chat.jsx
│       ├── HomeScreen.jsx
│       ├── LemonSliceAgentApp.jsx
│       ├── SwiggyDebugHarness.jsx
│       └── Tray.jsx
├── README.md
├── INSTRUCTIONS.md
└── build/config files
```

### Hosted Backend

- [`backend/server.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/backend/server.py)
  - FastAPI entrypoint.
  - Creates LemonSlice rooms and exposes the Swiggy transcript endpoints.
- [`backend/mistral_client.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/backend/mistral_client.py)
  - Small wrapper that forces Mistral planner responses into JSON.
- [`backend/orchestrator.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/backend/orchestrator.py)
  - Swiggy sidecar brain.
  - Holds session state, transcript gating, planner loop, confirmation checks, debug trace generation, and bridge message construction.
- [`backend/tests/test_orchestrator.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/backend/tests/test_orchestrator.py)
  - Behavioral tests for transcript gating, dedupe, echo suppression, and session continuity.

### Hosted Frontend

- [`src/App.jsx`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/src/App.jsx)
  - Root app switch between hosted avatar mode and text-only Swiggy debug mode.
- [`src/api.js`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/src/api.js)
  - Browser API wrapper for room creation and Swiggy transcript submission.
- [`src/providers/AgentStateProvider.tsx`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/src/providers/AgentStateProvider.tsx)
  - Shared UI state for agent join/readiness.
- [`src/components/LemonSliceAgentApp.jsx`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/src/components/LemonSliceAgentApp.jsx)
  - Main hosted runtime bridge.
  - Receives final `user_transcription` events, forwards them to the backend, suppresses bridge echoes, and injects commerce updates back into the room.
- [`src/components/SwiggyDebugHarness.jsx`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/src/components/SwiggyDebugHarness.jsx)
  - Text-only debug surface for exercising the existing sidecar directly.
- [`src/components/AgentCall.jsx`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/src/components/AgentCall.jsx)
  - Hosted call screen wrapper and agent video bootstrap behavior.
- [`src/components/AgentVideoTile.jsx`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/src/components/AgentVideoTile.jsx)
  - Daily video tile for the avatar participant.
- [`src/components/Chat.jsx`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/src/components/Chat.jsx)
  - Simple room chat panel for manual `chat-msg` sends.
- [`src/components/HomeScreen.jsx`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/src/components/HomeScreen.jsx)
  - Join screen for the hosted demo.
- [`src/components/Tray.jsx`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/src/components/Tray.jsx)
  - Call controls and chat tray shown during a hosted session.

### Hosted Runtime Docs

- [`realtime-agent/README.md`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/README.md)
  - Setup notes for the hosted merge.
- [`realtime-agent/INSTRUCTIONS.md`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/INSTRUCTIONS.md)
  - Local runbook, URLs, and terminal validation commands.
