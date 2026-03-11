import asyncio

import pytest

from reels_backend.idle import IdleSignalScheduler


@pytest.mark.asyncio
async def test_idle_signal_emitted_once_per_idle_window() -> None:
    calls: list[str] = []

    async def on_idle() -> None:
        calls.append("idle")

    scheduler = IdleSignalScheduler(idle_seconds=0, on_idle=on_idle)
    scheduler.arm()
    await asyncio.sleep(0.01)

    # No user activity means no second emission in the same idle window.
    await asyncio.sleep(0.01)
    assert calls == ["idle"]

    await scheduler.close()


@pytest.mark.asyncio
async def test_idle_signal_resets_after_user_activity() -> None:
    calls: list[str] = []

    async def on_idle() -> None:
        calls.append("idle")

    scheduler = IdleSignalScheduler(idle_seconds=0, on_idle=on_idle)
    scheduler.arm()
    await asyncio.sleep(0.01)
    assert calls == ["idle"]

    scheduler.notify_user_activity()
    await asyncio.sleep(0.01)
    assert calls == ["idle", "idle"]

    await scheduler.close()

