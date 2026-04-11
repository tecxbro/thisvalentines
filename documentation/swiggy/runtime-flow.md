# Swiggy Runtime Flow

## Current Runtime Split

There are two distinct ways the Swiggy integration can run.

### 1. Legacy direct-tool runtime

- A single live agent owns speech input, reasoning, and tool access.
- The agent mounts all available Swiggy MCP tools through [`swiggy_mcp.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/swiggy_mcp.py).
- The shared commerce prompt from [`instructions.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/instructions.py) tells that agent how to:
  - identify the Swiggy service
  - fetch saved addresses
  - search restaurants/products/slots
  - update carts
  - confirm before final purchase or booking actions

Flow:

```text
User speech
-> legacy runtime STT/LLM pipeline
-> live agent prompt + tool selection
-> direct Swiggy MCP tool call
-> live agent response
```

### 2. Hosted LemonSlice sidecar runtime

- LemonSlice Hosted owns the live avatar room and voice experience.
- The browser receives finalized `user_transcription` events from the room.
- The browser forwards those transcripts to the Swiggy backend sidecar.
- The backend sidecar decides whether to handle the turn, optionally calls Swiggy MCP tools, and returns a short commerce update.
- The browser injects that update back into the room as a `chat-msg`, which the avatar then relays naturally.

Flow:

```text
User speech
-> LemonSlice Hosted transcription
-> browser transcript bridge
-> FastAPI Swiggy sidecar
-> Mistral planner + Swiggy MCP tools
-> browser relay message
-> LemonSlice avatar response
```

## Hosted Sidecar Internals

### Session model

The hosted backend stores a lightweight in-memory session keyed by `session_id`.

Current state includes:

- `active_service`
- `flow_open`
- `pending_hint_service`
- recent user/tool/assistant events
- duplicate transcript hashes
- pending injected message hashes for bridge echo suppression

This state lives in [`backend/orchestrator.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/backend/orchestrator.py).

### Gate behavior

Before the planner runs, the sidecar uses a deterministic gate.

The gate answers:

- does this look like Swiggy commerce?
- if so, which service bucket?
- is the transcript actionable enough right now?

Current implementation details:

- keyword-based service detection
- service-specific “actionable enough” checks
- open-flow bypass for follow-ups
- hint recording for vague turns

This gate is intentionally cheap, but it is also the main current limitation because it can reject natural but vague commerce requests before Mistral ever sees them.

### Mistral’s role

Mistral is the planner, not the first-pass commerce detector.

Once the gate accepts a turn:

- the backend builds a prompt containing:
  - legacy Swiggy workflow instructions
  - current session state
  - recent session history
  - the current loop’s tool history
  - the full live tool catalog
- Mistral returns strict JSON with one of:
  - `noop`
  - `respond`
  - `tool_call`

### Confirmation behavior

The hosted backend protects the final money/booking tools:

- `place_food_order`
- `checkout`
- `book_table`

Those tools are blocked unless the latest transcript looks like an explicit confirmation.

This is a string-based safety check, not a full transactional approval state machine.

## Known Limitations

The current hosted sidecar intentionally keeps behavior simple, which creates a few important limitations:

- The gate can reject natural commerce turns before Mistral sees them.
- The backend does not receive the full hosted conversation transcript; it mainly sees user transcripts and its own injected follow-ups.
- Address, restaurant, and cart state are not fully normalized into structured fields yet.
- The backend cannot push directly into LemonSlice Hosted on its own; the browser is the relay.
- The current debug endpoint exposes rich traces, but normal backend stdout only shows request-level logs.

## Practical Review Guidance

When reading the code:

1. Start with [`swiggy_mcp_client.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/swiggy_mcp_client.py) to understand the shared tool layer.
2. Read [`instructions.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/instructions.py) to understand the intended commerce workflow.
3. Read [`backend/orchestrator.py`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/backend/orchestrator.py) to understand the hosted sidecar decisions.
4. Read [`src/components/LemonSliceAgentApp.jsx`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent/src/components/LemonSliceAgentApp.jsx) to understand the browser relay path.
