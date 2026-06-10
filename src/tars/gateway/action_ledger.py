from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from tars.core.db import Database

GENESIS_HASH = "0" * 64


def _compute_hash(prev_hash: str, session_id: str, tool: str, action: str) -> str:
    payload = f"{prev_hash}|{session_id}|{tool}|{action}"
    return hashlib.sha256(payload.encode()).hexdigest()


class ActionLedger:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def _get_prev_hash(self) -> str:
        row = await self.db.fetchone("SELECT hash FROM action_ledger ORDER BY seq DESC LIMIT 1")
        return row["hash"] if row else GENESIS_HASH

    async def append(
        self,
        session_id: str,
        tool: str,
        action: str,
        plan_step: str | None = None,
        result: str | None = None,
    ) -> str:
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        prev_hash = await self._get_prev_hash()
        entry_hash = _compute_hash(prev_hash, session_id, tool, action)

        await self.db.execute(
            """INSERT INTO action_ledger
               (prev_hash, timestamp, session_id, tool, action,
                plan_step, result, hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (prev_hash, now, session_id, tool, action, plan_step, result, entry_hash),
        )
        await self.db.commit()
        return entry_hash

    async def get_session_actions(self, session_id: str, limit: int = 100) -> list[dict]:
        rows = await self.db.fetchall(
            """SELECT * FROM action_ledger
               WHERE session_id = ?
               ORDER BY seq DESC LIMIT ?""",
            (session_id, limit),
        )
        return [dict(r) for r in rows]

    async def verify_chain(self) -> tuple[bool, int]:
        rows = await self.db.fetchall("SELECT * FROM action_ledger ORDER BY seq")
        prev = GENESIS_HASH
        for i, row in enumerate(rows):
            r = dict(row)
            expected = _compute_hash(prev, r["session_id"], r["tool"], r["action"])
            if expected != r["hash"] or r["prev_hash"] != prev:
                return False, i
            prev = r["hash"]
        return True, len(rows)
