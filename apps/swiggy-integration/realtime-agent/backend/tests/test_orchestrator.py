"""Behavioral tests for the hosted Swiggy sidecar orchestrator."""

from __future__ import annotations

import unittest

from backend.orchestrator import BrainOutcome, FOOD, SwiggyRealtimeOrchestrator


class FakeDecisionEngine:
    """Deterministic planner stub used to isolate orchestrator behavior."""

    def __init__(self, outcomes: list[BrainOutcome]) -> None:
        """Queue a finite list of planner outcomes for later test assertions."""
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, str]] = []

    async def run(self, state, transcript: str, service: str, debug_trace=None) -> BrainOutcome:
        """Record every invocation and return the next canned planner outcome."""
        self.calls.append((transcript, service))
        if not self._outcomes:
            raise AssertionError("No fake outcomes left for the decision engine")
        return self._outcomes.pop(0)


class SwiggyRealtimeOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    """Regression tests for transcript gating, flow state, and debug tracing."""

    async def test_non_commerce_transcript_is_noop(self) -> None:
        """Ignore turns that never enter the commerce gate."""
        engine = FakeDecisionEngine([])
        orchestrator = SwiggyRealtimeOrchestrator(decision_engine=engine)

        result = await orchestrator.handle_transcript(
            session_id="session-1",
            transcription="how are you doing today",
        )

        self.assertEqual(result["action"], "noop")
        self.assertEqual(result["reason"], "non_commerce")
        self.assertEqual(engine.calls, [])

    async def test_under_specified_food_transcript_records_hint_but_does_not_call_engine(self) -> None:
        """Keep a service hint for vague turns without invoking the planner yet."""
        engine = FakeDecisionEngine([])
        orchestrator = SwiggyRealtimeOrchestrator(decision_engine=engine)

        result = await orchestrator.handle_transcript(
            session_id="session-2",
            transcription="get me food",
        )

        self.assertEqual(result["action"], "noop")
        self.assertEqual(result["reason"], "needs_more_specificity")
        self.assertEqual(result["service"], FOOD)
        self.assertEqual(engine.calls, [])

    async def test_hint_follow_up_can_open_a_swiggy_flow(self) -> None:
        """Allow a later follow-up to activate the hinted commerce flow."""
        engine = FakeDecisionEngine(
            [
                BrainOutcome(
                    action="inject_message",
                    reason="found_options",
                    message="I found Biryani Blues. Want me to use your home address?",
                    service=FOOD,
                    flow_open=True,
                )
            ]
        )
        orchestrator = SwiggyRealtimeOrchestrator(decision_engine=engine)

        await orchestrator.handle_transcript(
            session_id="session-3",
            transcription="order food",
        )
        result = await orchestrator.handle_transcript(
            session_id="session-3",
            transcription="from Biryani Blues",
        )

        self.assertEqual(result["action"], "inject_message")
        self.assertEqual(result["service"], FOOD)
        self.assertEqual(engine.calls, [("from Biryani Blues", FOOD)])

    async def test_duplicate_transcript_is_deduplicated(self) -> None:
        """Prevent repeated final transcripts from replaying the same sidecar flow."""
        engine = FakeDecisionEngine(
            [
                BrainOutcome(
                    action="inject_message",
                    reason="search_started",
                    message="I found a couple of biryani options for you.",
                    service=FOOD,
                    flow_open=True,
                )
            ]
        )
        orchestrator = SwiggyRealtimeOrchestrator(decision_engine=engine)

        first = await orchestrator.handle_transcript(
            session_id="session-4",
            transcription="order biryani from Biryani Blues",
        )
        second = await orchestrator.handle_transcript(
            session_id="session-4",
            transcription="order biryani from Biryani Blues",
        )

        self.assertEqual(first["action"], "inject_message")
        self.assertEqual(second["action"], "noop")
        self.assertEqual(second["reason"], "duplicate_transcript")
        self.assertEqual(len(engine.calls), 1)

    async def test_bridge_echo_is_ignored(self) -> None:
        """Ignore the hosted relay message when it loops back as transcription."""
        engine = FakeDecisionEngine(
            [
                BrainOutcome(
                    action="inject_message",
                    reason="need_address",
                    message="I found Biryani Blues. Home or office?",
                    service=FOOD,
                    flow_open=True,
                )
            ]
        )
        orchestrator = SwiggyRealtimeOrchestrator(decision_engine=engine)

        first = await orchestrator.handle_transcript(
            session_id="session-5",
            transcription="order biryani from Biryani Blues",
        )
        second = await orchestrator.handle_transcript(
            session_id="session-5",
            transcription=first["chat_message"],
        )

        self.assertEqual(first["action"], "inject_message")
        self.assertEqual(second["action"], "noop")
        self.assertEqual(second["reason"], "bridge_echo")
        self.assertEqual(len(engine.calls), 1)

    async def test_active_flow_follow_up_uses_existing_service_context(self) -> None:
        """Keep follow-up turns inside the already-open service flow."""
        engine = FakeDecisionEngine(
            [
                BrainOutcome(
                    action="inject_message",
                    reason="need_address",
                    message="I found Biryani Blues. Home or office?",
                    service=FOOD,
                    flow_open=True,
                ),
                BrainOutcome(
                    action="inject_message",
                    reason="address_selected",
                    message="Got it. I'll use your home address.",
                    service=FOOD,
                    flow_open=True,
                ),
            ]
        )
        orchestrator = SwiggyRealtimeOrchestrator(decision_engine=engine)

        await orchestrator.handle_transcript(
            session_id="session-6",
            transcription="order biryani from Biryani Blues",
        )
        second = await orchestrator.handle_transcript(
            session_id="session-6",
            transcription="home address",
        )

        self.assertEqual(second["action"], "inject_message")
        self.assertEqual(engine.calls, [("order biryani from Biryani Blues", FOOD), ("home address", FOOD)])

    async def test_debug_trace_is_included_when_requested(self) -> None:
        """Expose planner/gate trace data only when the debug path requests it."""
        engine = FakeDecisionEngine(
            [
                BrainOutcome(
                    action="inject_message",
                    reason="found_options",
                    message="I found Biryani Blues. Home or office?",
                    service=FOOD,
                    flow_open=True,
                )
            ]
        )
        orchestrator = SwiggyRealtimeOrchestrator(decision_engine=engine)

        result = await orchestrator.handle_transcript(
            session_id="session-7",
            transcription="order biryani from Biryani Blues",
            include_debug_trace=True,
        )

        self.assertEqual(result["action"], "inject_message")
        self.assertIn("debug_trace", result)
        self.assertTrue(result["debug_trace"]["handled_by_sidecar"])
        self.assertEqual(result["debug_trace"]["gate"]["reason"], "actionable_transcript")
        self.assertEqual(result["debug_trace"]["final_outcome"]["reason"], "found_options")


if __name__ == "__main__":
    unittest.main()
