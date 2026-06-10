from __future__ import annotations

import asyncio

import pytest

from tars.core.events import Event, EventBus, EventType


@pytest.mark.asyncio
async def test_subscribe_and_emit() -> None:
    bus = EventBus()
    queue = bus.subscribe(EventType.TASK_COMPLETED)

    event = Event(type=EventType.TASK_COMPLETED, data={"goal": "test"})
    await bus.emit(event)

    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received.type == EventType.TASK_COMPLETED
    assert received.data["goal"] == "test"


@pytest.mark.asyncio
async def test_global_subscriber() -> None:
    bus = EventBus()
    queue = bus.subscribe()

    await bus.emit(Event(type=EventType.TASK_STARTED))
    await bus.emit(Event(type=EventType.TASK_COMPLETED))

    assert queue.qsize() == 2


@pytest.mark.asyncio
async def test_typed_subscriber_ignores_other_types() -> None:
    bus = EventBus()
    queue = bus.subscribe(EventType.KILL_SWITCH)

    await bus.emit(Event(type=EventType.TASK_STARTED))
    assert queue.empty()


@pytest.mark.asyncio
async def test_unsubscribe() -> None:
    bus = EventBus()
    queue = bus.subscribe(EventType.TASK_STARTED)
    bus.unsubscribe(queue, EventType.TASK_STARTED)

    await bus.emit(Event(type=EventType.TASK_STARTED))
    assert queue.empty()


def test_emit_nowait() -> None:
    bus = EventBus()
    queue = bus.subscribe(EventType.KILL_SWITCH)

    bus.emit_nowait(Event(type=EventType.KILL_SWITCH, data={"reason": "test"}))
    assert not queue.empty()
