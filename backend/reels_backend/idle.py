from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable


class IdleSignalScheduler:
    """
    Emits a single idle signal after N seconds of no user activity.

    Calling `notify_user_activity()` resets the timer and allows a new idle signal.

    Uses a threading.Timer for the wait so the 7s countdown never runs on the
    session's asyncio loop, avoiding any delay to the agent's STT/LLM/TTS pipeline.
    """

    def __init__(
        self,
        *,
        idle_seconds: int,
        on_idle: Callable[[], Awaitable[None]],
    ) -> None:
        self._idle_seconds = idle_seconds
        self._on_idle = on_idle
        self._timer: threading.Timer | None = None
        self._closed = False
        self._idle_emitted = False
        self._loop: asyncio.AbstractEventLoop | None = None

    def arm(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        if loop is not None:
            self._loop = loop
        else:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        self._schedule_idle_timer()

    def notify_user_activity(self) -> None:
        self._idle_emitted = False
        self._schedule_idle_timer()

    async def close(self) -> None:
        self._closed = True
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _schedule_idle_timer(self) -> None:
        if self._closed:
            return
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

        def fire() -> None:
            if self._closed or self._idle_emitted:
                return
            loop = self._loop
            if loop is None:
                return
            if loop.is_running():
                loop.call_soon_threadsafe(self._schedule_on_idle)

        self._timer = threading.Timer(self._idle_seconds, fire)
        self._timer.daemon = True
        self._timer.start()

    def _schedule_on_idle(self) -> None:
        if self._closed or self._idle_emitted:
            return
        loop = self._loop
        if loop is None:
            return
        asyncio.ensure_future(self._run_on_idle(loop), loop=loop)

    async def _run_on_idle(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._closed or self._idle_emitted:
            return
        try:
            await self._on_idle()
            self._idle_emitted = True
        except Exception:
            pass
        self._timer = None

