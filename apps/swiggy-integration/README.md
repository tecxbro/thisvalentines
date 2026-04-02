# Swiggy Integration App

Internal Swiggy integration app maintained on the `swiggy-integration` branch.

This app was imported into this repository as a standalone code snapshot and is intended to evolve independently from the `main` branch backend and frontend. There is no git linkage to the original source repository in this working tree.

## Current Runtime Shape

- Python application under `apps/swiggy-integration`
- MCP-driven Swiggy integration through `swiggy_mcp.py`
- Two browser-oriented entrypoints:
  - `swiggy_agent_one.py`
  - `swiggy_agent_two.py`
- One telephony-oriented entrypoint:
  - `swiggy_agent_phone.py`
- Interactive setup launcher:
  - `run.sh`

## Local Setup

```bash
cd apps/swiggy-integration
python3 -m venv venv
source venv/bin/activate
pip install -r requirement.txt
```

Create a local `.env` file with the runtime credentials used by this app:

```env
VIDEOSDK_AUTH_TOKEN=
GOOGLE_API_KEY=
DEEPGRAM_API_KEY=
CARTESIA_API_KEY=
```

Notes:

- `DEEPGRAM_API_KEY` and `CARTESIA_API_KEY` are required for `swiggy_agent_one.py`
- `swiggy_agent_two.py` uses the Gemini realtime path and does not need the Deepgram or Cartesia keys
- Swiggy login state is stored locally in `.swiggy_tokens.json`

## Running

Interactive setup:

```bash
cd apps/swiggy-integration
./run.sh
```

Manual commands:

```bash
cd apps/swiggy-integration
source venv/bin/activate
python swiggy_mcp.py
python swiggy_agent_one.py
```

Alternative entrypoints:

```bash
python swiggy_agent_two.py
python swiggy_agent_phone.py
```

## Repository Notes

- Keep work for this app on the `swiggy-integration` branch
- Use the separate worktree at `/Users/darshan/Documents/thisvalentines-swiggy-integration` for local development
- The preserved MIT license for the imported snapshot is in `LICENSE`
