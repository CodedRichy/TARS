from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from tars.core.db import Database


class Permission(BaseModel):
    id: int | None = None
    capability: str
    scope: str = "*"
    granted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    granted_by: str = "user"
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        if self.revoked_at:
            return False
        return not (self.expires_at and datetime.now(UTC) > self.expires_at)


class PermissionDeniedError(Exception):
    def __init__(self, capability: str, scope: str = "") -> None:
        self.capability = capability
        self.scope = scope
        msg = f"Permission denied: {capability}"
        if scope:
            msg += f" (scope: {scope})"
        super().__init__(msg)


class PermissionManager:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def grant(
        self,
        capability: str,
        scope: str = "*",
        granted_by: str = "user",
        expires_at: datetime | None = None,
    ) -> Permission:
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        exp = expires_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if expires_at else None
        await self.db.execute(
            """INSERT INTO permissions (capability, scope, granted_at, expires_at, granted_by)
               VALUES (?, ?, ?, ?, ?)""",
            (capability, scope, now, exp, granted_by),
        )
        await self.db.commit()
        row = await self.db.fetchone("SELECT * FROM permissions ORDER BY id DESC LIMIT 1")
        return _row_to_permission(row)

    async def revoke(self, capability: str, scope: str = "*") -> int:
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        await self.db.execute(
            """UPDATE permissions SET revoked_at = ?
               WHERE capability = ? AND scope = ? AND revoked_at IS NULL""",
            (now, capability, scope),
        )
        await self.db.commit()
        row = await self.db.fetchone("SELECT changes() as cnt")
        return row["cnt"] if row else 0

    async def revoke_all(self) -> int:
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        await self.db.execute(
            "UPDATE permissions SET revoked_at = ? WHERE revoked_at IS NULL",
            (now,),
        )
        await self.db.commit()
        row = await self.db.fetchone("SELECT changes() as cnt")
        return row["cnt"] if row else 0

    async def check(self, capability: str, scope: str = "") -> bool:
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        row = await self.db.fetchone(
            """SELECT id FROM permissions
               WHERE capability = ? AND revoked_at IS NULL
               AND (expires_at IS NULL OR expires_at > ?)
               AND (scope = '*' OR scope = ?)
               LIMIT 1""",
            (capability, now, scope),
        )
        return row is not None

    async def require(self, capability: str, scope: str = "") -> None:
        if not await self.check(capability, scope):
            raise PermissionDeniedError(capability, scope)

    async def list_active(self) -> list[Permission]:
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        rows = await self.db.fetchall(
            """SELECT * FROM permissions
               WHERE revoked_at IS NULL
               AND (expires_at IS NULL OR expires_at > ?)
               ORDER BY granted_at DESC""",
            (now,),
        )
        return [_row_to_permission(r) for r in rows]

    async def list_all(self) -> list[Permission]:
        rows = await self.db.fetchall("SELECT * FROM permissions ORDER BY granted_at DESC")
        return [_row_to_permission(r) for r in rows]


def _row_to_permission(row: dict | object) -> Permission:
    r = dict(row) if not isinstance(row, dict) else row
    return Permission(
        id=r["id"],
        capability=r["capability"],
        scope=r["scope"],
        granted_at=r["granted_at"],
        expires_at=r.get("expires_at"),
        granted_by=r["granted_by"],
        revoked_at=r.get("revoked_at"),
    )
