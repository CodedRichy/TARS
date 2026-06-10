from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ulid import ULID


class SessionStatus(enum.StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    COMPLETED = "completed"
    KILLED = "killed"


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(ULID()))
    channel: str = "cli"
    status: SessionStatus = SessionStatus.IDLE
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    current_task: str | None = None
    task_count: int = 0
    total_cost_inr: float = 0.0

    def touch(self) -> None:
        self.last_activity = datetime.now(UTC)

    def start_task(self, goal: str) -> None:
        self.status = SessionStatus.ACTIVE
        self.current_task = goal
        self.touch()

    def complete_task(self, cost_inr: float = 0.0) -> None:
        self.status = SessionStatus.IDLE
        self.current_task = None
        self.task_count += 1
        self.total_cost_inr += cost_inr
        self.touch()

    def kill(self) -> None:
        self.status = SessionStatus.KILLED
        self.current_task = None


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, channel: str = "cli") -> Session:
        session = Session(channel=channel)
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_active(self) -> list[Session]:
        return [
            s
            for s in self._sessions.values()
            if s.status in (SessionStatus.ACTIVE, SessionStatus.IDLE)
        ]

    def kill_all(self) -> int:
        count = 0
        for s in self._sessions.values():
            if s.status in (SessionStatus.ACTIVE, SessionStatus.IDLE):
                s.kill()
                count += 1
        return count

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    @property
    def count(self) -> int:
        return len(self._sessions)
