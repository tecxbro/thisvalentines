"""Hosted Swiggy sidecar orchestration, gating, and debug trace logic."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

SWIGGY_ROOT = Path(__file__).resolve().parents[2]
if str(SWIGGY_ROOT) not in sys.path:
    sys.path.insert(0, str(SWIGGY_ROOT))

from instructions import SWIGGY_AGENT_INSTRUCTIONS


FOOD = "food"
INSTAMART = "instamart"
DINEOUT = "dineout"
CONFIRMATION_TOOLS = {"place_food_order", "checkout", "book_table"}

SERVICE_KEYWORDS = {
    FOOD: {
        "order",
        "food",
        "hungry",
        "biryani",
        "pizza",
        "burger",
        "meal",
        "lunch",
        "dinner",
        "breakfast",
        "restaurant",
    },
    INSTAMART: {
        "grocery",
        "groceries",
        "instamart",
        "milk",
        "eggs",
        "bread",
        "vegetables",
        "fruit",
        "snacks",
        "cooking",
    },
    DINEOUT: {
        "dineout",
        "book",
        "reservation",
        "reserve",
        "table",
        "restaurant",
        "date",
        "party",
        "dinner",
        "lunch",
    },
}

GENERIC_SERVICE_WORDS = {
    FOOD: {
        "food",
        "order",
        "hungry",
        "eat",
        "lunch",
        "dinner",
        "breakfast",
        "meal",
        "something",
        "get",
        "want",
        "need",
        "me",
        "please",
    },
    INSTAMART: {
        "groceries",
        "grocery",
        "instamart",
        "items",
        "stuff",
        "get",
        "want",
        "need",
        "me",
        "please",
    },
    DINEOUT: {
        "book",
        "table",
        "reservation",
        "restaurant",
        "dineout",
        "reserve",
        "dinner",
        "lunch",
        "date",
        "night",
        "please",
        "me",
    },
}

FOLLOW_UP_HINT_WORDS = {
    "from",
    "at",
    "for",
    "home",
    "office",
    "yes",
    "yeah",
    "confirm",
    "place",
    "book",
    "checkout",
    "second",
    "first",
    "tonight",
    "tomorrow",
    "today",
}


class ToolClientProtocol(Protocol):
    """Minimal tool client surface needed by the planner loop."""

    async def list_tools(self) -> list[Any]:
        ...

    async def call_tool(self, tool_name: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


class PlannerClientProtocol(Protocol):
    """Minimal text-planner interface used by the decision engine."""

    async def generate_json(self, prompt: str) -> dict[str, Any]:
        ...


@dataclass
class SessionEvent:
    """Single event kept in per-session history for planner context."""

    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)


@dataclass
class SessionState:
    """Mutable in-memory state for one hosted Swiggy conversation session."""

    session_id: str
    active_service: str | None = None
    flow_open: bool = False
    pending_hint_service: str | None = None
    pending_hint_at: float = 0.0
    recent_events: deque[SessionEvent] = field(default_factory=lambda: deque(maxlen=18))
    recent_transcript_hashes: dict[str, float] = field(default_factory=dict)
    pending_injected_hashes: dict[str, float] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


@dataclass
class GateDecision:
    """Result of the fast pre-planner gate for a single transcript."""

    service: str | None
    should_handle: bool
    reason: str
    record_hint: bool = False


@dataclass
class BrainOutcome:
    """Planner result normalized for the outer orchestrator."""

    action: str
    reason: str
    message: str | None = None
    service: str | None = None
    flow_open: bool | None = None
    tool_events: list[SessionEvent] = field(default_factory=list)


@dataclass
class DebugPlannerStep:
    """Serializable trace record for one planner/tool iteration."""

    step: int
    planner_action: dict[str, Any]
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    tool_service: str | None = None
    tool_result_text: str | None = None
    blocked_by_confirmation: bool = False


@dataclass
class DebugTrace:
    """Top-level debug trace returned by the debug transcript endpoint."""

    gate: dict[str, Any] = field(default_factory=dict)
    handled_by_sidecar: bool = False
    planner_steps: list[dict[str, Any]] = field(default_factory=list)
    final_outcome: dict[str, Any] = field(default_factory=dict)


class SwiggyDecisionEngine:
    """Runs the Mistral planner loop and executes MCP tools one step at a time."""

    def __init__(
        self,
        swiggy_client: ToolClientProtocol,
        planner_client: PlannerClientProtocol,
        max_steps: int = 5,
    ) -> None:
        """Store the shared tool client, planner client, and loop limit."""
        self._swiggy_client = swiggy_client
        self._planner_client = planner_client
        self._max_steps = max_steps

    async def run(
        self,
        state: SessionState,
        transcript: str,
        service: str,
        debug_trace: DebugTrace | None = None,
    ) -> BrainOutcome:
        """Plan and execute up to `max_steps` Swiggy actions for one turn."""
        tools = await self._swiggy_client.list_tools()
        tool_map = {tool.name: tool for tool in tools}
        tool_events: list[SessionEvent] = []

        for step_index in range(self._max_steps):
            # Each iteration re-prompts the planner with the latest tool output so
            # the model can either answer the user or request one more tool call.
            prompt = self._build_prompt(state, transcript, service, tools, tool_events)
            decision = await self._planner_client.generate_json(prompt)
            action = self._coerce_action(decision)
            action_type = action["type"]
            step_trace = DebugPlannerStep(
                step=step_index + 1,
                planner_action=to_debug_jsonable(action),
            )

            if action_type == "noop":
                _append_debug_step(debug_trace, step_trace)
                return BrainOutcome(
                    action="noop",
                    reason=action.get("reason", "model_noop"),
                    service=action.get("active_service") or service,
                    flow_open=bool(action.get("flow_open", state.flow_open)),
                    tool_events=tool_events,
                )

            if action_type == "respond":
                message = _normalize_text(action.get("message", ""))
                if not message:
                    _append_debug_step(debug_trace, step_trace)
                    return BrainOutcome(
                        action="noop",
                        reason="empty_model_response",
                        service=action.get("active_service") or service,
                        flow_open=bool(action.get("flow_open", state.flow_open)),
                        tool_events=tool_events,
                    )
                _append_debug_step(debug_trace, step_trace)
                return BrainOutcome(
                    action="inject_message",
                    reason=action.get("reason", "model_response"),
                    message=message,
                    service=action.get("active_service") or service,
                    flow_open=self._resolve_flow_open(action, message, state.flow_open),
                    tool_events=tool_events,
                )

            tool_name = action["tool_name"]
            step_trace.tool_name = tool_name
            if tool_name not in tool_map:
                _append_debug_step(debug_trace, step_trace)
                return BrainOutcome(
                    action="inject_message",
                    reason="unknown_tool",
                    message="I hit a Swiggy integration mismatch while checking that. Try again in a moment.",
                    service=service,
                    flow_open=True,
                    tool_events=tool_events,
                )

            if tool_name in CONFIRMATION_TOOLS and not _looks_like_explicit_confirmation(transcript):
                # Final purchase/booking tools are guarded even if the planner
                # tries to invoke them before the user has explicitly confirmed.
                step_trace.blocked_by_confirmation = True
                step_trace.arguments = to_debug_jsonable(action.get("arguments") or {})
                _append_debug_step(debug_trace, step_trace)
                return BrainOutcome(
                    action="inject_message",
                    reason="confirmation_required",
                    message="I can do that once you confirm. Want me to go ahead?",
                    service=service,
                    flow_open=True,
                    tool_events=tool_events,
                )

            arguments = action.get("arguments")
            if not isinstance(arguments, dict):
                arguments = {}
            step_trace.arguments = to_debug_jsonable(arguments)

            try:
                tool_result = await self._swiggy_client.call_tool(tool_name, arguments)
            except Exception:
                _append_debug_step(debug_trace, step_trace)
                return BrainOutcome(
                    action="inject_message",
                    reason="tool_error",
                    message="Swiggy hit an error while I was checking that. Try again in a moment.",
                    service=service,
                    flow_open=True,
                    tool_events=tool_events,
                )

            step_trace.tool_service = str(tool_result.get("service") or "")
            step_trace.tool_result_text = (tool_result.get("text") or "")[:1500]
            _append_debug_step(debug_trace, step_trace)
            tool_events.append(
                SessionEvent(
                    role="tool",
                    content=tool_result.get("text", "")[:4000],
                    metadata={
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "service": tool_result.get("service"),
                    },
                )
            )

        return BrainOutcome(
            action="inject_message",
            reason="max_steps_reached",
            message="I'm still checking Swiggy. Give me a second and ask again if needed.",
            service=service,
            flow_open=True,
            tool_events=tool_events,
        )

    def _build_prompt(
        self,
        state: SessionState,
        transcript: str,
        service: str,
        tools: list[Any],
        tool_events: list[SessionEvent],
    ) -> str:
        """Build the planner prompt from state, transcript, and live tool data."""
        tool_catalog = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "service": getattr(tool, "service", service),
            }
            for tool in tools
        ]
        history = [
            {
                "role": event.role,
                "content": event.content,
                "metadata": event.metadata,
            }
            for event in list(state.recent_events)[-8:]
        ]
        loop_history = [
            {
                "role": event.role,
                "content": event.content,
                "metadata": event.metadata,
            }
            for event in tool_events
        ]

        return (
            "You are the Swiggy commerce sidecar for a hosted LemonSlice avatar. "
            "The avatar already handles normal conversation. Only take over when a transcript is "
            "specific enough for Swiggy commerce or when a Swiggy flow is already open.\n\n"
            f"{SWIGGY_AGENT_INSTRUCTIONS}\n\n"
            "Return JSON only with one of these shapes:\n"
            '{"type":"noop","reason":"short_reason","active_service":"food|instamart|dineout|null","flow_open":false}\n'
            '{"type":"respond","reason":"short_reason","message":"short user-facing reply","active_service":"food|instamart|dineout|null","flow_open":true}\n'
            '{"type":"tool_call","reason":"short_reason","tool_name":"exact_tool_name","arguments":{},"active_service":"food|instamart|dineout|null","flow_open":true}\n\n'
            "Rules:\n"
            "- One tool call at a time.\n"
            "- Never fabricate Swiggy data.\n"
            "- Never place an order, checkout, or book a table without explicit confirmation.\n"
            "- Keep responses short and voice-friendly.\n"
            "- If you need more information, respond with a single concise question.\n"
            "- When a tool result is enough, respond naturally; do not mention MCP, tools, backend, or system updates.\n\n"
            f"Current target service: {service}\n"
            f"Session state: {json.dumps({'active_service': state.active_service, 'flow_open': state.flow_open, 'pending_hint_service': state.pending_hint_service})}\n"
            f"Recent session history: {json.dumps(history, ensure_ascii=True)}\n"
            f"Current loop tool history: {json.dumps(loop_history, ensure_ascii=True)}\n"
            f"Latest user transcript: {json.dumps(transcript, ensure_ascii=True)}\n"
            f"Available tools: {json.dumps(tool_catalog, ensure_ascii=True)}\n"
        )

    def _coerce_action(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize invalid planner output into a safe noop action."""
        action_type = raw.get("type")
        if action_type not in {"noop", "respond", "tool_call"}:
            return {"type": "noop", "reason": "invalid_model_action"}
        return raw

    def _resolve_flow_open(
        self, action: dict[str, Any], message: str, current_flow_open: bool
    ) -> bool:
        """Infer whether the commerce flow should stay open after a reply."""
        if "flow_open" in action:
            return bool(action["flow_open"])
        lowered = message.lower()
        if message.endswith("?"):
            return True
        if any(keyword in lowered for keyword in ("confirm", "which one", "home", "office", "what time")):
            return True
        if any(keyword in lowered for keyword in ("placed", "booked", "checked out")):
            return False
        return current_flow_open


class SwiggyRealtimeOrchestrator:
    """Coordinates session state, transcript gating, planning, and relay output."""

    def __init__(
        self,
        decision_engine: SwiggyDecisionEngine,
        session_ttl_seconds: int = 1800,
        duplicate_ttl_seconds: int = 45,
        hint_ttl_seconds: int = 180,
        injected_ttl_seconds: int = 120,
    ) -> None:
        """Configure TTLs for session memory, hints, duplicates, and echoes."""
        self._decision_engine = decision_engine
        self._session_ttl_seconds = session_ttl_seconds
        self._duplicate_ttl_seconds = duplicate_ttl_seconds
        self._hint_ttl_seconds = hint_ttl_seconds
        self._injected_ttl_seconds = injected_ttl_seconds
        self._sessions: dict[str, SessionState] = {}
        self._sessions_lock = asyncio.Lock()

    async def handle_transcript(
        self,
        session_id: str,
        transcription: str,
        event_type: str = "user_transcription",
        client_timestamp: str | None = None,
        include_debug_trace: bool = False,
    ) -> dict[str, Any]:
        """Handle one hosted user transcript and return a bridge-side decision."""
        transcript = _normalize_text(transcription)
        debug_trace = DebugTrace() if include_debug_trace else None
        if not session_id or not transcript:
            return _attach_debug_trace(
                {"action": "noop", "reason": "empty_input"},
                debug_trace,
            )
        if event_type != "user_transcription":
            return _attach_debug_trace(
                {"action": "noop", "reason": "unsupported_event_type"},
                debug_trace,
            )

        state = await self._get_session(session_id)
        async with state.lock:
            self._purge_state(state)
            state.updated_at = time.monotonic()

            transcript_hash = _stable_hash(transcript)
            if transcript_hash in state.pending_injected_hashes:
                # Hosted relay messages can reappear as user_transcription events;
                # suppress them so the sidecar does not re-handle its own output.
                del state.pending_injected_hashes[transcript_hash]
                return _attach_debug_trace(
                    {"action": "noop", "reason": "bridge_echo"},
                    debug_trace,
                )
            if transcript_hash in state.recent_transcript_hashes:
                return _attach_debug_trace(
                    {"action": "noop", "reason": "duplicate_transcript"},
                    debug_trace,
                )

            state.recent_transcript_hashes[transcript_hash] = state.updated_at
            state.recent_events.append(
                SessionEvent(
                    role="user",
                    content=transcript,
                    metadata={
                        "event_type": event_type,
                        "client_timestamp": client_timestamp,
                    },
                )
            )

            gate = self._evaluate_gate(state, transcript)
            if debug_trace is not None:
                debug_trace.gate = {
                    "reason": gate.reason,
                    "service": gate.service,
                    "should_handle": gate.should_handle,
                    "record_hint": gate.record_hint,
                    "detected_service": _detect_service(transcript),
                    "pending_hint_service": state.pending_hint_service,
                    "flow_open_before": state.flow_open,
                    "active_service_before": state.active_service,
                }
            if not gate.should_handle:
                if gate.record_hint and gate.service:
                    # Vague Swiggy turns leave behind a short-lived service hint so
                    # the next specific follow-up can enter the sidecar directly.
                    state.pending_hint_service = gate.service
                    state.pending_hint_at = state.updated_at
                if debug_trace is not None:
                    debug_trace.handled_by_sidecar = False
                return _attach_debug_trace(
                    {"action": "noop", "reason": gate.reason, "service": gate.service},
                    debug_trace,
                )

            if debug_trace is not None:
                debug_trace.handled_by_sidecar = True
            outcome = await self._decision_engine.run(
                state,
                transcript,
                gate.service or FOOD,
                debug_trace=debug_trace,
            )
            for event in outcome.tool_events:
                state.recent_events.append(event)

            resolved_service = outcome.service or gate.service
            if resolved_service:
                state.active_service = resolved_service

            if outcome.action != "inject_message" or not outcome.message:
                state.flow_open = bool(outcome.flow_open)
                if not state.flow_open:
                    state.active_service = None
                return _attach_debug_trace({
                    "action": "noop",
                    "reason": outcome.reason,
                    "service": resolved_service,
                }, debug_trace, outcome, state)

            state.flow_open = bool(outcome.flow_open)
            if not state.flow_open:
                state.pending_hint_service = None
                state.active_service = None
            else:
                state.pending_hint_service = resolved_service
                state.pending_hint_at = state.updated_at

            chat_message = build_hosted_chat_message(outcome.message)
            # Track the exact injected relay payload so it can be ignored if the
            # hosted room echoes that same text back as a transcript event later.
            state.pending_injected_hashes[_stable_hash(_normalize_text(chat_message))] = (
                state.updated_at
            )
            state.recent_events.append(
                SessionEvent(
                    role="assistant",
                    content=outcome.message,
                    metadata={"service": resolved_service, "reason": outcome.reason},
                )
            )

            return _attach_debug_trace({
                "action": "inject_message",
                "reason": outcome.reason,
                "service": resolved_service,
                "message": outcome.message,
                "chat_message": chat_message,
                "flow_open": state.flow_open,
            }, debug_trace, outcome, state)

    async def _get_session(self, session_id: str) -> SessionState:
        """Return an existing session or create a new one after TTL cleanup."""
        now = time.monotonic()
        async with self._sessions_lock:
            expired = [
                key
                for key, state in self._sessions.items()
                if now - state.updated_at > self._session_ttl_seconds
            ]
            for key in expired:
                del self._sessions[key]

            state = self._sessions.get(session_id)
            if state is None:
                state = SessionState(session_id=session_id)
                self._sessions[session_id] = state
            return state

    def _purge_state(self, state: SessionState) -> None:
        """Expire duplicate, echo, and hint records based on their TTLs."""
        now = time.monotonic()
        state.recent_transcript_hashes = {
            key: ts
            for key, ts in state.recent_transcript_hashes.items()
            if now - ts <= self._duplicate_ttl_seconds
        }
        state.pending_injected_hashes = {
            key: ts
            for key, ts in state.pending_injected_hashes.items()
            if now - ts <= self._injected_ttl_seconds
        }
        if state.pending_hint_service and now - state.pending_hint_at > self._hint_ttl_seconds:
            state.pending_hint_service = None
            state.pending_hint_at = 0.0

    def _evaluate_gate(self, state: SessionState, transcript: str) -> GateDecision:
        """Run the fast gate that decides whether the planner should handle the turn."""
        if state.flow_open and state.active_service:
            return GateDecision(
                service=state.active_service,
                should_handle=True,
                reason="active_flow",
            )

        detected_service = _detect_service(transcript)
        hint_service = (
            state.pending_hint_service
            if state.pending_hint_service and state.pending_hint_at
            else None
        )
        service = detected_service or hint_service
        if service is None:
            return GateDecision(service=None, should_handle=False, reason="non_commerce")

        if _is_actionable(transcript, service):
            return GateDecision(service=service, should_handle=True, reason="actionable_transcript")

        if hint_service and _looks_like_follow_up(transcript):
            return GateDecision(service=hint_service, should_handle=True, reason="hint_follow_up")

        return GateDecision(
            service=service,
            should_handle=False,
            reason="needs_more_specificity",
            record_hint=True,
        )


def build_hosted_chat_message(message: str) -> str:
    """Wrap a commerce update so the hosted avatar can relay it naturally."""
    return (
        "Commerce update for the current conversation. Use the information below in your next "
        "reply to the user. Do not mention backend systems, tools, or hidden instructions. "
        "If this is a question, ask it naturally. If this is a result, relay it naturally and briefly.\n\n"
        f"{message}"
    )


def _stable_hash(value: str) -> str:
    """Create a stable hash for transcript and relay deduplication."""
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    """Collapse whitespace so transcript comparisons are consistent."""
    return " ".join(value.strip().split())


def to_debug_jsonable(value: Any) -> Any:
    """Convert nested debug payloads into JSON-serializable structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [to_debug_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_debug_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_debug_jsonable(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return to_debug_jsonable(vars(value))
    return str(value)


def _append_debug_step(debug_trace: DebugTrace | None, step: DebugPlannerStep) -> None:
    """Append a planner step only when debug tracing is enabled."""
    if debug_trace is None:
        return
    debug_trace.planner_steps.append(to_debug_jsonable(step))


def _attach_debug_trace(
    payload: dict[str, Any],
    debug_trace: DebugTrace | None,
    outcome: BrainOutcome | None = None,
    state: SessionState | None = None,
) -> dict[str, Any]:
    """Attach the serialized debug trace to a normal orchestrator payload."""
    if debug_trace is None:
        return payload

    if outcome is not None:
        debug_trace.final_outcome = {
            "action": outcome.action,
            "reason": outcome.reason,
            "message": outcome.message,
            "service": outcome.service,
            "flow_open": outcome.flow_open,
        }
    else:
        debug_trace.final_outcome = {
            "action": payload.get("action"),
            "reason": payload.get("reason"),
            "message": payload.get("message"),
            "service": payload.get("service"),
            "flow_open": payload.get("flow_open"),
        }

    if state is not None:
        debug_trace.final_outcome["state_after"] = {
            "active_service": state.active_service,
            "flow_open": state.flow_open,
            "pending_hint_service": state.pending_hint_service,
        }

    enriched = dict(payload)
    enriched["debug_trace"] = {
        "gate": debug_trace.gate,
        "handled_by_sidecar": debug_trace.handled_by_sidecar,
        "planner_steps": debug_trace.planner_steps,
        "final_outcome": debug_trace.final_outcome,
    }
    return enriched


def _detect_service(transcript: str) -> str | None:
    """Classify a transcript into food, Instamart, Dineout, or unknown."""
    lowered = transcript.lower()
    scores = {FOOD: 0, INSTAMART: 0, DINEOUT: 0}
    for service, keywords in SERVICE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lowered:
                scores[service] += 1

    if scores[DINEOUT] and any(word in lowered for word in ("table", "reservation", "book", "reserve")):
        return DINEOUT
    if scores[INSTAMART] > scores[FOOD]:
        return INSTAMART
    if scores[FOOD] >= scores[DINEOUT] and scores[FOOD] > 0:
        return FOOD
    if scores[DINEOUT] > 0:
        return DINEOUT
    return None


def _is_actionable(transcript: str, service: str) -> bool:
    """Decide whether a transcript is specific enough to enter the planner."""
    lowered = transcript.lower()
    tokens = [token.strip(".,!?") for token in lowered.split()]
    specific_tokens = [token for token in tokens if token and token not in GENERIC_SERVICE_WORDS[service]]

    if service == FOOD:
        return ("from " in lowered) or len(specific_tokens) >= 1 and "food" not in specific_tokens
    if service == INSTAMART:
        return len(specific_tokens) >= 1
    if service == DINEOUT:
        has_time = any(word in lowered for word in ("today", "tonight", "tomorrow", "pm", "am"))
        has_party_size = any(token.isdigit() for token in tokens)
        return ("at " in lowered) or has_time or has_party_size or len(specific_tokens) >= 2
    return False


def _looks_like_follow_up(transcript: str) -> bool:
    """Detect short follow-ups that should reuse a recently hinted service."""
    lowered = transcript.lower()
    tokens = lowered.split()
    return (
        any(word in lowered for word in FOLLOW_UP_HINT_WORDS)
        or any(token.isdigit() for token in tokens)
        or len(tokens) >= 2
    )


def _looks_like_explicit_confirmation(transcript: str) -> bool:
    """Detect the small set of phrases that unlock final money/book tools."""
    lowered = transcript.lower()
    return any(
        phrase in lowered
        for phrase in (
            "yes",
            "yeah",
            "yep",
            "confirm",
            "go ahead",
            "place it",
            "book it",
            "checkout",
            "do it",
        )
    )
