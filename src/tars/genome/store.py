from __future__ import annotations

import json
from datetime import UTC, datetime

from ulid import ULID

from tars.core.db import Database
from tars.genome.confidence import compute_confidence
from tars.genome.models import (
    Episode,
    Evidence,
    EvidenceDirection,
    FailureModel,
    Heuristic,
    HeuristicStatus,
    OriginType,
    Scope,
    row_to_episode,
    row_to_evidence,
    row_to_heuristic,
)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id() -> str:
    return str(ULID())


class GenomeStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    # --- Episodes ---

    async def insert_episode(self, episode: Episode) -> str:
        eid = episode.id or _new_id()
        await self.db.execute(
            """INSERT INTO episode
               (id, goal, context_features, action_trace, outcome, outcome_detail,
                lessons_applied, failure_models_checked, cost_breakdown,
                started_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                eid,
                episode.goal,
                json.dumps(episode.context_features),
                json.dumps(episode.action_trace),
                episode.outcome.value,
                episode.outcome_detail,
                json.dumps(episode.lessons_applied),
                json.dumps(episode.failure_models_checked),
                episode.cost_breakdown.model_dump_json(),
                str(episode.started_at),
                str(episode.completed_at),
            ),
        )
        await self.db.commit()
        return eid

    async def get_episode(self, episode_id: str) -> Episode | None:
        row = await self.db.fetchone("SELECT * FROM episode WHERE id = ?", (episode_id,))
        return row_to_episode(row) if row else None

    async def list_episodes(
        self, since: datetime | None = None, outcome: str | None = None, limit: int = 100
    ) -> list[Episode]:
        sql = "SELECT * FROM episode WHERE 1=1"
        params: list = []
        if since:
            sql += " AND completed_at >= ?"
            params.append(str(since))
        if outcome:
            sql += " AND outcome = ?"
            params.append(outcome)
        sql += " ORDER BY completed_at DESC LIMIT ?"
        params.append(limit)
        rows = await self.db.fetchall(sql, params)
        return [row_to_episode(r) for r in rows]

    # --- Heuristics ---

    async def insert_heuristic(
        self,
        statement: str,
        scope: Scope | None = None,
        origin_type: OriginType = OriginType.EXTRACTED,
        origin_episode_id: str | None = None,
        initial_supporting: float = 0,
        initial_contradicting: float = 0,
    ) -> Heuristic:
        hid = _new_id()
        now = _now()
        scope = scope or Scope()
        conf = compute_confidence(initial_supporting, initial_contradicting)
        await self.db.execute(
            """INSERT INTO heuristic
               (id, statement, scope, status, supporting, contradicting, confidence,
                origin_type, origin_episode_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                hid,
                statement,
                scope.model_dump_json(),
                HeuristicStatus.CANDIDATE.value,
                initial_supporting,
                initial_contradicting,
                conf,
                origin_type.value,
                origin_episode_id,
                now,
                now,
            ),
        )
        await self.db.commit()
        return Heuristic(
            id=hid,
            statement=statement,
            scope=scope,
            status=HeuristicStatus.CANDIDATE,
            supporting=initial_supporting,
            contradicting=initial_contradicting,
            confidence=conf,
            origin_type=origin_type,
            origin_episode_id=origin_episode_id,
            created_at=now,
            updated_at=now,
        )

    async def get_heuristic(self, heuristic_id: str) -> Heuristic | None:
        row = await self.db.fetchone("SELECT * FROM heuristic WHERE id = ?", (heuristic_id,))
        return row_to_heuristic(row) if row else None

    async def list_heuristics(
        self, status: HeuristicStatus | None = None, limit: int = 200
    ) -> list[Heuristic]:
        if status:
            rows = await self.db.fetchall(
                "SELECT * FROM heuristic WHERE status = ? ORDER BY confidence DESC LIMIT ?",
                (status.value, limit),
            )
        else:
            rows = await self.db.fetchall(
                "SELECT * FROM heuristic ORDER BY confidence DESC LIMIT ?", (limit,)
            )
        return [row_to_heuristic(r) for r in rows]

    async def update_heuristic_status(self, heuristic_id: str, new_status: HeuristicStatus) -> None:
        now = _now()
        extra = ""
        if new_status == HeuristicStatus.ACTIVE:
            extra = ", promoted_at = ?"
        elif new_status in (HeuristicStatus.DEPRECATED, HeuristicStatus.REVERTED):
            extra = ", deprecated_at = ?"

        sql = f"UPDATE heuristic SET status = ?, updated_at = ?{extra} WHERE id = ?"
        params: list = [new_status.value, now]
        if extra:
            params.append(now)
        params.append(heuristic_id)
        await self.db.execute(sql, params)
        await self.db.commit()

    async def update_heuristic_confidence(
        self, heuristic_id: str, supporting: float, contradicting: float
    ) -> float:
        conf = compute_confidence(supporting, contradicting)
        now = _now()
        await self.db.execute(
            """UPDATE heuristic
               SET supporting = ?, contradicting = ?, confidence = ?,
                   last_evidence_at = ?, updated_at = ?
               WHERE id = ?""",
            (supporting, contradicting, conf, now, now, heuristic_id),
        )
        await self.db.commit()
        return conf

    async def mark_applied(self, heuristic_id: str) -> None:
        await self.db.execute(
            "UPDATE heuristic SET last_applied_at = ? WHERE id = ?",
            (_now(), heuristic_id),
        )
        await self.db.commit()

    # --- Evidence ---

    async def add_evidence(
        self,
        heuristic_id: str,
        episode_id: str,
        direction: EvidenceDirection,
        weight: float = 1.0,
        reasoning: str | None = None,
        is_origin: bool = False,
    ) -> Evidence:
        eid = _new_id()
        await self.db.execute(
            """INSERT INTO evidence
               (id, heuristic_id, episode_id, direction, weight, reasoning, is_origin)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (eid, heuristic_id, episode_id, direction.value, weight, reasoning, int(is_origin)),
        )
        await self.db.commit()

        totals = await self._compute_evidence_totals(heuristic_id)
        await self.update_heuristic_confidence(heuristic_id, totals[0], totals[1])

        return Evidence(
            id=eid,
            heuristic_id=heuristic_id,
            episode_id=episode_id,
            direction=direction,
            weight=weight,
            reasoning=reasoning,
            is_origin=is_origin,
        )

    async def get_evidence_for_heuristic(self, heuristic_id: str) -> list[Evidence]:
        rows = await self.db.fetchall(
            "SELECT * FROM evidence WHERE heuristic_id = ? ORDER BY created_at",
            (heuristic_id,),
        )
        return [row_to_evidence(r) for r in rows]

    async def zero_evidence_weights(self, heuristic_id: str) -> None:
        await self.db.execute(
            "UPDATE evidence SET weight = 0.0 WHERE heuristic_id = ?",
            (heuristic_id,),
        )
        await self.db.commit()

    async def count_fresh_supporting(self, heuristic_id: str) -> int:
        row = await self.db.fetchone(
            """SELECT COUNT(*) as cnt FROM evidence
               WHERE heuristic_id = ? AND is_origin = 0
               AND weight >= 0.8 AND direction = 'SUPPORTING'""",
            (heuristic_id,),
        )
        return row["cnt"] if row else 0

    async def _compute_evidence_totals(self, heuristic_id: str) -> tuple[float, float]:
        rows = await self.db.fetchall(
            """SELECT direction, SUM(weight) as total
               FROM evidence WHERE heuristic_id = ? AND weight > 0
               GROUP BY direction""",
            (heuristic_id,),
        )
        supporting = 0.0
        contradicting = 0.0
        for r in rows:
            if r["direction"] == EvidenceDirection.SUPPORTING.value:
                supporting = r["total"]
            else:
                contradicting = r["total"]
        return supporting, contradicting

    # --- Failure Models ---

    async def insert_failure_model(self, fm: FailureModel) -> str:
        fid = fm.id or _new_id()
        now = _now()
        await self.db.execute(
            """INSERT INTO failure_model
               (id, signature, root_cause, recovery_path, scope,
                source_episodes, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fid,
                fm.signature,
                fm.root_cause,
                json.dumps(fm.recovery_path),
                fm.scope.model_dump_json(),
                json.dumps(fm.source_episodes),
                fm.status.value,
                now,
                now,
            ),
        )
        await self.db.commit()
        return fid

    async def list_active_failure_models(self) -> list[FailureModel]:
        rows = await self.db.fetchall("SELECT * FROM failure_model WHERE status = 'ACTIVE'")
        result = []
        for r in rows:
            r = dict(r)
            result.append(
                FailureModel(
                    id=r["id"],
                    signature=r["signature"],
                    root_cause=r["root_cause"],
                    recovery_path=json.loads(r["recovery_path"]),
                    scope=Scope(**json.loads(r["scope"])),
                    trigger_count=r["trigger_count"],
                    last_triggered_at=r.get("last_triggered_at"),
                    source_episodes=json.loads(r["source_episodes"]),
                    status=r["status"],
                    created_at=r.get("created_at"),
                    updated_at=r.get("updated_at"),
                )
            )
        return result
