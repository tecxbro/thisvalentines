# Swiggy Integration App

Internal Swiggy integration app maintained on the `swiggy-integration` branch.

This app was imported into this repository as a standalone code snapshot and is intended to evolve independently from the `main` branch backend and frontend. There is no git linkage to the original source repository in this working tree.

## Current Runtime Shape

- Python application under `apps/swiggy-integration`
- Hosted LemonSlice + Swiggy sidecar app under `realtime-agent/`
- Shared MCP-driven Swiggy integration through `swiggy_mcp_client.py`
- Two browser-oriented entrypoints:
  - `swiggy_agent_one.py`
  - `swiggy_agent_two.py`
- One telephony-oriented entrypoint:
  - `swiggy_agent_phone.py`
- Interactive setup launcher:
  - `run.sh`

## Primary Runtime

Use `apps/swiggy-integration/realtime-agent` for the hosted LemonSlice merge. This is now the main runtime for the live avatar + Swiggy sidecar flow.

The older `swiggy_agent_one.py`, `swiggy_agent_two.py`, and `swiggy_agent_phone.py` files are kept as legacy/reference code for the previous VideoSDK-based architecture.

## Hosted Runtime Setup

```bash
cd apps/swiggy-integration/realtime-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pnpm install
```

Create a local `.env` file from `realtime-agent/.env.example`:

```env
LEMONSLICE_AGENT_ID=
LEMONSLICE_API_KEY=
MISTRAL_API_KEY=
```

Notes:

- Swiggy login state is stored locally in `.swiggy_tokens.json`
- The hosted backend uses the same shared Swiggy OAuth token file
- The hosted backend loads `realtime-agent/.env.local` first and falls back to `backend/.env.local`
- You still need to manually update the LemonSlice hosted agent prompt in the LemonSlice playground so it tolerates backend-injected commerce updates

## Running

Hosted runtime:

```bash
cd apps/swiggy-integration/realtime-agent
pnpm start
```

Legacy runtime setup:

```bash
cd apps/swiggy-integration
source venv/bin/activate
pip install -r requirement.txt
python swiggy_mcp.py
```

Legacy runtime entrypoints:

```bash
python swiggy_agent_one.py
python swiggy_agent_two.py
python swiggy_agent_phone.py
```

## Repository Notes

- Keep work for this app on the `swiggy-integration` branch
- Use the separate worktree at `/Users/darshan/Documents/thisvalentines-swiggy-integration` for local development
- The preserved MIT license for the imported snapshot is in `LICENSE`
