from __future__ import annotations

import asyncio

import pytest

from tars.core.events import Event, EventBus, EventType
from tars.core.stream import EventStream


@pytest.mark.asyncio
async def test_stream_yields_all_events() -> None:
    bus = EventBus()
    stream = EventStream(bus)

    bus.emit_nowait(Event(type=EventType.TASK_STARTED, data={"goal": "test"}))
    bus.emit_nowait(Event(type=EventType.TASK_COMPLETED, data={"goal": "test"}))

    events: list[Event] = []
    for _ in range(2):
        ev = await asyncio.wait_for(stream.__anext__(), timeout=1.0)
        events.append(ev)

    assert len(events) == 2
    assert events[0].type == EventType.TASK_STARTED
    assert events[1].type == EventType.TASK_COMPLETED

    stream.close()


@pytest.mark.asyncio
async def test_stream_filters_by_session_id() -> None:
    bus = EventBus()
    stream = EventStream(bus, session_id="session-A")

    bus.emit_nowait(Event(type=EventType.STEP_STARTED, session_id="session-B"))
    bus.emit_nowait(Event(type=EventType.STEP_STARTED, session_id="session-A", data={"idx": 1}))

    ev = await asyncio.wait_for(stream.__anext__(), timeout=1.0)
    assert ev.session_id == "session-A"
    assert ev.data["idx"] == 1

    stream.close()


@pytest.mark.asyncio
async def test_stream_close_stops_iteration() -> None:
    bus = EventBus()
    stream = EventStream(bus)
    stream.close()

    with pytest.raises(StopAsyncIteration):
        await stream.__anext__()


@pytest.mark.asyncio
async def test_stream_context_manager() -> None:
    bus = EventBus()
    async with EventStream(bus) as stream:
        bus.emit_nowait(Event(type=EventType.TASK_STARTED))
        ev = await asyncio.wait_for(stream.__anext__(), timeout=1.0)
        assert ev.type == EventType.TASK_STARTED

    assert stream._closed


@pytest.mark.asyncio
async def test_stream_unsubscribes_on_close() -> None:
    bus = EventBus()
    stream = EventStream(bus)
    assert len(bus._global_subscribers) == 1

    stream.close()
    assert len(bus._global_subscribers) == 0
