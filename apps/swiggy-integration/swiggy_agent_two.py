"""
Swiggy voice entrypoint using Gemini native audio.

Single model handles STT + LLM + TTS for a lower-latency setup.
Requires the runtime auth token and Google API key.
"""

from videosdk.agents import (
    Agent,
    AgentSession,
    Pipeline,
    JobContext,
    RoomOptions,
    WorkerJob,
)
from videosdk.plugins.google import GeminiRealtime, GeminiLiveConfig

from instructions import SWIGGY_AGENT_INSTRUCTIONS, GREETING, GOODBYE
from swiggy_mcp import build_swiggy_mcp_servers

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


class SwiggyVoiceAgent(Agent):
    """Legacy Swiggy agent backed by Gemini's native realtime audio model."""

    def __init__(self):
        """Configure the agent with the shared prompt and Swiggy tools."""
        super().__init__(
            instructions=SWIGGY_AGENT_INSTRUCTIONS,
            mcp_servers=build_swiggy_mcp_servers(),
        )

    async def on_enter(self):
        """Greet the user when the agent joins the room."""
        await self.session.say(GREETING)

    async def on_exit(self):
        """Close the conversation when the session shuts down."""
        await self.session.say(GOODBYE)


async def entrypoint(ctx: JobContext):
    """Boot the Gemini realtime pipeline and attach the Swiggy agent."""
    model = GeminiRealtime(
        model="gemini-3.1-flash-live-preview",
        config=GeminiLiveConfig(
            voice="Leda",
            response_modalities=["AUDIO"],
        ),
    )

    pipeline = Pipeline(llm=model)
    agent = SwiggyVoiceAgent()

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
    """Run the Gemini-native Swiggy agent as a worker job."""
    job = WorkerJob(
        entrypoint=entrypoint,
        jobctx=make_context,
    )
    job.start()
