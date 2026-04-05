"""
Swiggy phone-oriented voice entrypoint.

Registers the agent for inbound and outbound SIP-style telephony flows.

Setup:
  1. Run `./run.sh` or `python swiggy_mcp.py` to log into Swiggy
  2. Configure the telephony routing used by your runtime account
  3. Run `python swiggy_agent_phone.py`
"""

import asyncio
import logging

from videosdk.agents import (
    Agent,
    AgentSession,
    Pipeline,
    JobContext,
    RoomOptions,
    WorkerJob,
    Options,
)
from videosdk.plugins.google import GeminiRealtime, GeminiLiveConfig

from instructions import SWIGGY_AGENT_INSTRUCTIONS, GREETING, GOODBYE
from swiggy_mcp import build_swiggy_mcp_servers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


class SwiggyPhoneAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions=SWIGGY_AGENT_INSTRUCTIONS,
            mcp_servers=build_swiggy_mcp_servers(),
        )

    async def on_enter(self):
        await self.session.say(GREETING)

    async def on_exit(self):
        await self.session.say(GOODBYE)


async def entrypoint(ctx: JobContext):
    model = GeminiRealtime(
        model="gemini-3.1-flash-live-preview",
        config=GeminiLiveConfig(
            voice="Leda",
            response_modalities=["AUDIO"],
        ),
    )

    pipeline = Pipeline(llm=model)
    agent = SwiggyPhoneAgent()

    session = AgentSession(
        agent=agent,
        pipeline=pipeline,
    )

    await session.start(
        wait_for_participant=True,
        run_until_shutdown=True,
    )


def make_context() -> JobContext:
    return JobContext(room_options=RoomOptions())


if __name__ == "__main__":
    options = Options(
        agent_id="SwiggyVoiceAgent",
        register=True,
        max_processes=10,
        host="localhost",
        port=8081,
    )

    job = WorkerJob(
        entrypoint=entrypoint,
        jobctx=make_context,
        options=options,
    )
    job.start()
