from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from tars.core.db import Database
from tars.genome.models import ChangelogEntry, ChangeOperation, row_to_changelog

GENESIS_HASH = "0" * 64


def _compute_hash(prev_hash: str, operation: str, entity_id: str, field_changes: str) -> str:
    payload = f"{prev_hash}|{operation}|{entity_id}|{field_changes}"
    return hashlib.sha256(payload.encode()).hexdigest()


class ChangelogManager:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def _get_prev_hash(self) -> str:
        row = await self.db.fetchone("SELECT hash FROM changelog ORDER BY seq DESC LIMIT 1")
        return row["hash"] if row else GENESIS_HASH

    async def append(
        self,
        entity_type: str,
        entity_id: str,
        operation: ChangeOperation,
        field_changes: dict | None = None,
        reason: str | None = None,
        snapshot: dict | None = None,
    ) -> ChangelogEntry:
        field_changes = field_changes or {}
        snapshot = snapshot or {}
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        prev_hash = await self._get_prev_hash()
        changes_json = json.dumps(field_changes, sort_keys=True)
        entry_hash = _compute_hash(prev_hash, operation.value, entity_id, changes_json)

        await self.db.execute(
            """INSERT INTO changelog
               (hash, prev_hash, timestamp, entity_type, entity_id,
                operation, field_changes, reason, snapshot)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_hash,
                prev_hash,
                now,
                entity_type,
                entity_id,
                operation.value,
                changes_json,
                reason,
                json.dumps(snapshot, sort_keys=True),
            ),
        )
        await self.db.commit()

        return ChangelogEntry(
            hash=entry_hash,
            prev_hash=prev_hash,
            timestamp=now,
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            field_changes=field_changes,
            reason=reason,
            snapshot=snapshot,
        )

    async def get_log(
        self,
        entity_type: str | None = None,
        entity_id: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[ChangelogEntry]:
        sql = "SELECT * FROM changelog WHERE 1=1"
        params: list = []
        if entity_type:
            sql += " AND entity_type = ?"
            params.append(entity_type)
        if entity_id:
            sql += " AND entity_id = ?"
            params.append(entity_id)
        if since:
            sql += " AND timestamp >= ?"
            params.append(str(since))
        sql += " ORDER BY seq DESC LIMIT ?"
        params.append(limit)
        rows = await self.db.fetchall(sql, params)
        return [row_to_changelog(r) for r in rows]

    async def get_entries_since(self, since: datetime) -> list[ChangelogEntry]:
        rows = await self.db.fetchall(
            "SELECT * FROM changelog WHERE timestamp >= ? ORDER BY seq",
            (str(since),),
        )
        return [row_to_changelog(r) for r in rows]

    async def verify_chain(self) -> tuple[bool, int]:
        rows = await self.db.fetchall("SELECT * FROM changelog ORDER BY seq")
        prev = GENESIS_HASH
        for i, row in enumerate(rows):
            r = dict(row)
            expected = _compute_hash(prev, r["operation"], r["entity_id"], r["field_changes"])
            if expected != r["hash"] or r["prev_hash"] != prev:
                return False, i
            prev = r["hash"]
        return True, len(rows)
