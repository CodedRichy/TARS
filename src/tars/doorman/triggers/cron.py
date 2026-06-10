from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime

from croniter import croniter


@dataclass
class CronTrigger:
    expression: str
    task_goal: str
    domain: str = ""
    tags: list[str] | None = None

    @property
    def is_valid(self) -> bool:
        return croniter.is_valid(self.expression)

    def next_fire(self, base: datetime | None = None) -> datetime:
        base = base or datetime.now(UTC)
        cron = croniter(self.expression, base)
        return cron.get_next(datetime).replace(tzinfo=UTC)

    def seconds_until_next(self, base: datetime | None = None) -> float:
        nxt = self.next_fire(base)
        now = base or datetime.now(UTC)
        return max(0, (nxt - now).total_seconds())


class CronScheduler:
    def __init__(self) -> None:
        self._triggers: list[CronTrigger] = []
        self._running = False
        self._task: asyncio.Task | None = None

    def add_trigger(self, trigger: CronTrigger) -> None:
        if trigger.is_valid:
            self._triggers.append(trigger)

    @property
    def trigger_count(self) -> int:
        return len(self._triggers)

    async def start(self, callback) -> None:
        self._running = True
        self._task = asyncio.create_task(self._loop(callback))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self, callback) -> None:
        while self._running:
            if not self._triggers:
                await asyncio.sleep(60)
                continue

            nearest = min(t.seconds_until_next() for t in self._triggers)
            await asyncio.sleep(max(1, nearest))

            now = datetime.now(UTC)
            for trigger in self._triggers:
                nxt = trigger.next_fire(datetime.fromtimestamp(now.timestamp() - 2, tz=UTC))
                if abs((nxt - now).total_seconds()) < 2:
                    await callback(trigger)
