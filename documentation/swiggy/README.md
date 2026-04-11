# Swiggy Documentation

This folder is the Swiggy-specific source of truth for the code under [`apps/swiggy-integration`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration).

## Overview

The Swiggy integration currently has two runtime shapes:

- Legacy VideoSDK runtime:
  - One live voice agent owns speech, reasoning, and direct MCP tool access.
  - Entry points: `swiggy_agent_one.py`, `swiggy_agent_two.py`, `swiggy_agent_phone.py`
- Hosted LemonSlice runtime:
  - LemonSlice Hosted owns the live avatar room and voice experience.
  - A backend sidecar receives user transcripts, uses Mistral plus live Swiggy MCP tools, and relays commerce updates back into the same session.
  - Primary runtime path: `apps/swiggy-integration/realtime-agent`

## Which Runtime Is Primary

The hosted LemonSlice merge under [`apps/swiggy-integration/realtime-agent`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/realtime-agent) is the primary runtime today.

The legacy VideoSDK files are still kept because they are useful for:

- reference architecture
- direct-tool agent behavior comparison
- phone-oriented runtime support

## Reading Order

If you are new to the codebase, read these docs in this order:

1. [file-structure.md](/Users/darshan/Documents/thisvalentines/documentation/swiggy/file-structure.md)
2. [runtime-flow.md](/Users/darshan/Documents/thisvalentines/documentation/swiggy/runtime-flow.md)
3. The top-level app README at [`apps/swiggy-integration/README.md`](/Users/darshan/Documents/thisvalentines/apps/swiggy-integration/README.md)
