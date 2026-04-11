"""
Swiggy voice entrypoint with a multi-provider pipeline.

Pipeline: Deepgram STT + Google Gemini LLM + Cartesia TTS.
Requires the runtime auth token plus Google, Deepgram, and Cartesia keys.
"""

from videosdk.agents import (
    Agent,
    AgentSession,
    Pipeline,
    JobContext,
    RoomOptions,
    WorkerJob
)
from videosdk.plugins.google import GoogleLLM
from videosdk.plugins.deepgram import DeepgramSTT
from videosdk.plugins.cartesia import CartesiaTTS
from videosdk.plugins.silero import SileroVAD
from videosdk.plugins.turn_detector import TurnDetector, pre_download_model

from instructions import SWIGGY_AGENT_INSTRUCTIONS, GREETING, GOODBYE
from swiggy_mcp import build_swiggy_mcp_servers

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

pre_download_model()


class SwiggyVoiceAgent(Agent):
    """Legacy voice agent that mounts the full Swiggy MCP tool catalog."""

    def __init__(self):
        """Configure the agent with the shared Swiggy instructions and tools."""
        super().__init__(
            instructions=SWIGGY_AGENT_INSTRUCTIONS,
            mcp_servers=build_swiggy_mcp_servers(),
        )

    async def on_enter(self):
        """Greet the user when the legacy agent joins a room."""
        await self.session.say(GREETING)

    async def on_exit(self):
        """Close the session with a short spoken goodbye."""
        await self.session.say(GOODBYE)


async def entrypoint(ctx: JobContext):
    """Boot the multi-provider speech pipeline and attach the Swiggy agent."""
    agent = SwiggyVoiceAgent()

    pipeline = Pipeline(
        stt=DeepgramSTT(),
        llm=GoogleLLM(),
        tts=CartesiaTTS(),
        vad=SileroVAD(),
        turn_detector=TurnDetector(),
    )

    session = AgentSession(
        agent=agent,
        pipeline=pipeline,
    )

    await session.start(
        wait_for_participant=True,
        run_until_shutdown=True,
    )


def make_context() -> JobContext:
    """Create the default playground room configuration for local testing."""
    return JobContext(
        room_options=RoomOptions(
            name="Swiggy Voice Agent",
            playground=True,
        )
    )


if __name__ == "__main__":
    """Run the legacy multi-provider Swiggy agent as a worker job."""
    job = WorkerJob(
        entrypoint=entrypoint,
        jobctx=make_context,
    )
    job.start()
