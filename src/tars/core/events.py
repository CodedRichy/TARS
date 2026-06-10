from __future__ import annotations

import asyncio
import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


class EventType(enum.StrEnum):
    TASK_SUBMITTED = "task_submitted"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    PERMISSION_REQUESTED = "permission_requested"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    KILL_SWITCH = "kill_switch"
    CORRECTION_RECEIVED = "correction_received"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"


@dataclass
class Event:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    session_id: str = ""


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[asyncio.Queue[Event]]] = {}
        self._global_subscribers: list[asyncio.Queue[Event]] = []

    def subscribe(self, event_type: EventType | None = None) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        if event_type is None:
            self._global_subscribers.append(queue)
        else:
            self._subscribers.setdefault(event_type, []).append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Event], event_type: EventType | None = None) -> None:
        if event_type is None:
            if queue in self._global_subscribers:
                self._global_subscribers.remove(queue)
        else:
            subs = self._subscribers.get(event_type, [])
            if queue in subs:
                subs.remove(queue)

    async def emit(self, event: Event) -> None:
        typed_subs = self._subscribers.get(event.type, [])
        for q in typed_subs:
            await q.put(event)
        for q in self._global_subscribers:
            await q.put(event)

    def emit_nowait(self, event: Event) -> None:
        typed_subs = self._subscribers.get(event.type, [])
        for q in typed_subs:
            q.put_nowait(event)
        for q in self._global_subscribers:
            q.put_nowait(event)
