from __future__ import annotations

from datetime import UTC, datetime

from tars.agent.permissions import PermissionManager
from tars.core.events import Event, EventBus, EventType
from tars.gateway.session import SessionManager


class KillSwitch:
    def __init__(
        self,
        session_manager: SessionManager,
        permission_manager: PermissionManager,
        event_bus: EventBus,
    ) -> None:
        self.sessions = session_manager
        self.permissions = permission_manager
        self.event_bus = event_bus
        self._triggered = False
        self._triggered_at: datetime | None = None

    @property
    def is_triggered(self) -> bool:
        return self._triggered

    async def trigger(self, reason: str = "manual kill") -> dict:
        self._triggered = True
        self._triggered_at = datetime.now(UTC)

        killed_sessions = self.sessions.kill_all()
        revoked_perms = await self.permissions.revoke_all()

        self.event_bus.emit_nowait(
            Event(
                type=EventType.KILL_SWITCH,
                data={
                    "reason": reason,
                    "killed_sessions": killed_sessions,
                    "revoked_permissions": revoked_perms,
                },
            )
        )

        return {
            "triggered_at": self._triggered_at.isoformat(),
            "reason": reason,
            "killed_sessions": killed_sessions,
            "revoked_permissions": revoked_perms,
        }

    def reset(self) -> None:
        self._triggered = False
        self._triggered_at = None
