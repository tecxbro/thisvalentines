# LemonSlice Realtime Agent + Swiggy Sidecar

A React application that uses LemonSlice Hosted for the live avatar experience and a local Swiggy sidecar backend for commerce actions.

## Overview

This application now showcases how to:

- Securely connect to the LemonSlice API
- Create Daily.co rooms and integrate it with a LemonSlice agent
- Join video calls with the agent
- Listen to LemonSlice hosted transcription events
- Route concrete Swiggy requests through the Swiggy MCP sidecar
- Feed Swiggy results back into the same live conversation

## Prerequisites

- Node.js 18+ and pnpm
- Python 3.8+ and pip
- A LemonSlice API key
- A LemonSlice agent ID
- A Mistral API key for the Swiggy sidecar planner
- A completed Swiggy OAuth login stored in `../.swiggy_tokens.json`

> **⚠️ Security Note:** Never expose your API token in client-side code. Always use a self-hosted endpoint to securely handle API calls with your token on the server side.

## Installation

```bash
# Install frontend dependencies
pnpm install

# Install backend dependencies
pip install -r requirements.txt
```

## Environment Setup

Create a `.env` file based on `.env.example` in the root directory with the following variables:

```env
LEMONSLICE_AGENT_ID=your_agent_id
LEMONSLICE_API_KEY=your_api_key
MISTRAL_API_KEY=your_mistral_api_key
MISTRAL_MODEL=mistral-small-latest
```

Manual LemonSlice setup:

- Update the hosted LemonSlice agent prompt in the LemonSlice playground so the hosted agent handles general chat, avoids inventing Swiggy facts, and accepts backend-injected commerce guidance naturally.
- The backend loads `realtime-agent/.env.local` first, then falls back to `backend/.env.local` so it can reuse the same local keys as the old backend.

## Start the servers

1. Start the frontend and backend server concurrently
```bash
pnpm start
```
2. Navigate to `http://localhost:5173`

## Architecture

This application consists of two parts:

1. **Frontend (React)**: Joins the Daily room, listens for hosted `user_transcription` events, and forwards concrete transcripts to the backend
2. **Backend (FastAPI)**: Creates LemonSlice Hosted rooms and runs the Swiggy sidecar orchestrator

## Creating a Room

The application creates a Daily.co room by calling the LemonSlice API through the backend server. Here's how it works:

### Backend Server (`backend/server.py`)

The backend server provides a `/create-room` endpoint that securely calls the current LemonSlice Hosted API:

```python
@app.post("/create-room")
async def create_room():
    agent_id = os.getenv("LEMONSLICE_AGENT_ID")
    api_key = os.getenv("LEMONSLICE_API_KEY")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://lemonslice.com/api/liveai/rooms",
            headers={"X-API-Key": api_key},
            json={"agent_id": agent_id},
        )
        data = response.json()
        return {"room_url": data["room_url"], "token": data["token"]}
```

The server:
- Reads `LEMONSLICE_AGENT_ID` and `LEMONSLICE_API_KEY` from environment variables
- Makes a POST request to `https://lemonslice.com/api/liveai/rooms` with the API key in headers
- Returns the `room_url`, `token`, and `session_id` needed by the frontend

### Frontend API Client (`src/api.js`)

The frontend calls the backend server to get the room URL:

```javascript
async function createRoom() {
  const endpoint = "http://localhost:3000/create-room";
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  });
  return response.json(); // Returns { room_url: "..." }
}
```

This keeps the LemonSlice API key secure on the server side and never exposes it to the client.

## Swiggy Sidecar Bridge

The frontend listens for LemonSlice Hosted `user_transcription` events. When a finalized transcript is specific enough for Swiggy, the backend:

- Evaluates whether the transcript should engage Swiggy or stay as normal hosted conversation
- Uses Mistral text planning plus the Swiggy MCP tools to decide the next commerce step
- Returns a single bridge message that the frontend sends back into the same Daily room via `chat-msg`

Echo suppression is built in on both sides so backend-injected `chat-msg` prompts do not loop back into Swiggy again.

## Sending Messages to the Agent

Messages are sent to the agent using Daily's `sendAppMessage` function. This code lives in `src/components/Chat.jsx`. The message format is:

```javascript
sendAppMessage(
  {
    event: "chat-msg",
    message: "Your message here",
    name: "User",
  },
  "*", // Send to all participants
);
```

## Listening to Agent Events

The application listens to agent events using Daily's `useDailyEvent` hook with the `"app-message"` event type. Events are handled in `src/components/LemonSliceAgentApp.jsx`:

```javascript
useDailyEvent(
  "app-message",
  useCallback((ev) => {
    // Handle different event types
    if (ev?.data?.type === "bot_ready") {
      setIsAgentReady(true);
    }
    // ... other event handlers
  }, []),
);
```

## Sending Control Events

You can also send control events to the agent:

### Force End

Forcefully end the agent session:

```javascript
sendAppMessage({ event: "force-end" }, "*");
```
