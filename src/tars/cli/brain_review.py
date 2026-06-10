from __future__ import annotations

from datetime import UTC, datetime

from tars.core.db import Database
from tars.genome.changelog import ChangelogManager
from tars.genome.models import ChangeOperation, HeuristicStatus
from tars.genome.store import GenomeStore


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class BrainReviewEngine:
    def __init__(self, db: Database, store: GenomeStore) -> None:
        self.db = db
        self.store = store

    async def create_pr(self, heuristic_id: str) -> int:
        await self.db.execute(
            "INSERT INTO brain_pr (heuristic_id) VALUES (?)",
            (heuristic_id,),
        )
        await self.db.commit()
        row = await self.db.fetchone(
            "SELECT pr_number FROM brain_pr WHERE heuristic_id = ? "
            "ORDER BY pr_number DESC LIMIT 1",
            (heuristic_id,),
        )
        return row["pr_number"] if row else 0

    async def list_pending(self) -> list[dict]:
        rows = await self.db.fetchall(
            """SELECT bp.pr_number, bp.heuristic_id, bp.created_at,
                      h.statement, h.confidence, h.supporting, h.contradicting
               FROM brain_pr bp
               JOIN heuristic h ON h.id = bp.heuristic_id
               WHERE bp.status = 'PENDING'
               ORDER BY bp.pr_number""",
        )
        return [dict(r) for r in rows]

    async def get_pr(self, pr_number: int) -> dict | None:
        row = await self.db.fetchone(
            """SELECT bp.*, h.statement, h.confidence, h.supporting,
                      h.contradicting, h.status as h_status
               FROM brain_pr bp
               JOIN heuristic h ON h.id = bp.heuristic_id
               WHERE bp.pr_number = ?""",
            (pr_number,),
        )
        return dict(row) if row else None

    async def approve(
        self, pr_number: int, resolved_by: str = "user",
    ) -> bool:
        pr = await self.get_pr(pr_number)
        if not pr or pr["status"] != "PENDING":
            return False

        now = _now()
        await self.db.execute(
            """UPDATE brain_pr
               SET status = 'APPROVED', resolved_by = ?, resolved_at = ?
               WHERE pr_number = ?""",
            (resolved_by, now, pr_number),
        )

        await self.store.update_heuristic_status(
            pr["heuristic_id"], HeuristicStatus.ACTIVE,
        )

        cl = ChangelogManager(self.db)
        await cl.append(
            entity_type="HEURISTIC",
            entity_id=pr["heuristic_id"],
            operation=ChangeOperation.UPDATE,
            reason=f"brain PR #{pr_number} approved by {resolved_by}",
            field_changes={"status": "ACTIVE"},
            snapshot={"statement": pr["statement"]},
        )
        return True

    async def reject(
        self, pr_number: int, reason: str = "",
        resolved_by: str = "user",
    ) -> bool:
        pr = await self.get_pr(pr_number)
        if not pr or pr["status"] != "PENDING":
            return False

        now = _now()
        await self.db.execute(
            """UPDATE brain_pr
               SET status = 'REJECTED', reason = ?,
                   resolved_by = ?, resolved_at = ?
               WHERE pr_number = ?""",
            (reason, resolved_by, now, pr_number),
        )
        await self.db.commit()
        return True

    async def auto_approve_eligible(
        self, min_confidence: float = 0.85,
        min_evidence: int = 5,
    ) -> list[int]:
        pending = await self.list_pending()
        approved = []
        for pr in pending:
            if (
                pr["confidence"] >= min_confidence
                and pr["supporting"] >= min_evidence
            ):
                ok = await self.approve(pr["pr_number"], resolved_by="auto")
                if ok:
                    approved.append(pr["pr_number"])
        return approved
