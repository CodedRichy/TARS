from __future__ import annotations

import asyncio
from typing import AsyncIterator

from tars.core.events import Event, EventBus


class EventStream:
    """Async iterator over EventBus events, optionally filtered by session_id.

    This is the universal streaming primitive consumed by WebSocket, SSE,
    and channel adapters.
    """

    def __init__(
        self,
        event_bus: EventBus,
        session_id: str | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._session_id = session_id
        self._queue = event_bus.subscribe()
        self._closed = False

    def close(self) -> None:
        if not self._closed:
            self._event_bus.unsubscribe(self._queue)
            self._closed = True

    def __aiter__(self) -> AsyncIterator[Event]:
        return self

    async def __anext__(self) -> Event:
        if self._closed:
            raise StopAsyncIteration
        while True:
            try:
                event = await self._queue.get()
            except asyncio.CancelledError:
                self.close()
                raise StopAsyncIteration
            if self._session_id and event.session_id != self._session_id:
                continue
            return event

    async def __aenter__(self) -> EventStream:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.close()
