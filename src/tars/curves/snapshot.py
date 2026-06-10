from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta

from ulid import ULID

from tars.core.db import Database


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_id() -> str:
    return str(ULID())


class SnapshotCollector:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def collect_daily(self, date: str | None = None) -> dict:
        date = date or datetime.now(UTC).strftime("%Y-%m-%d")
        return await self._collect("daily", date, date, date)

    async def collect_weekly(self, week_label: str | None = None) -> dict:
        now = datetime.now(UTC)
        if week_label:
            year, week = week_label.split("-W")
            start = datetime.strptime(f"{year}-W{week}-1", "%Y-W%W-%w").replace(tzinfo=UTC)
        else:
            start = now - timedelta(days=now.weekday())
            week_label = f"{start.year}-W{start.isocalendar()[1]:02d}"
        start_str = start.strftime("%Y-%m-%d")
        end_str = (start + timedelta(days=6)).strftime("%Y-%m-%d")
        return await self._collect("weekly", week_label, start_str, end_str)

    async def collect_monthly(self, month_label: str | None = None) -> dict:
        now = datetime.now(UTC)
        if month_label:
            year, month = month_label.split("-")
            start = datetime(int(year), int(month), 1, tzinfo=UTC)
        else:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_label = start.strftime("%Y-%m")
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        end -= timedelta(days=1)
        return await self._collect(
            "monthly", month_label,
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
        )

    async def _collect(
        self, period_type: str, period_label: str,
        start_date: str, end_date: str,
    ) -> dict:
        existing = await self.db.fetchone(
            "SELECT id FROM improvement_snapshot WHERE period_type = ? AND period_label = ?",
            (period_type, period_label),
        )
        if existing:
            row = await self.db.fetchone(
                "SELECT * FROM improvement_snapshot WHERE id = ?",
                (existing["id"],),
            )
            return dict(row) if row else {}

        task_metrics = await self._task_metrics(start_date, end_date)
        brain_metrics = await self._brain_metrics(start_date, end_date)
        cost_metrics = await self._cost_metrics(start_date, end_date)
        growth_score = self._compute_growth_score(task_metrics, brain_metrics, cost_metrics)
        deltas = await self._compute_deltas(period_type, task_metrics, growth_score, brain_metrics)

        sid = _new_id()
        await self.db.execute(
            """INSERT INTO improvement_snapshot
               (id, period_type, period_label,
                total_episodes, success_count, partial_count, failure_count, success_rate,
                total_lessons, active_lessons, candidate_lessons,
                promoted_count, reverted_count,
                avg_confidence, p50_confidence, p90_confidence,
                total_cost_inr, cost_per_task, cost_per_success,
                growth_score,
                delta_success_rate, delta_growth_score,
                delta_active_lessons, delta_cost_per_task)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sid, period_type, period_label,
                task_metrics["total_episodes"], task_metrics["success"],
                task_metrics["partial"], task_metrics["failure"],
                task_metrics["success_rate"],
                brain_metrics["total_lessons"], brain_metrics["active"],
                brain_metrics["candidate"],
                brain_metrics["promoted"], brain_metrics["reverted"],
                brain_metrics["avg_confidence"],
                brain_metrics["p50_confidence"],
                brain_metrics["p90_confidence"],
                cost_metrics["total_cost"],
                cost_metrics["cost_per_task"],
                cost_metrics["cost_per_success"],
                growth_score,
                deltas.get("delta_success_rate"),
                deltas.get("delta_growth_score"),
                deltas.get("delta_active_lessons"),
                deltas.get("delta_cost_per_task"),
            ),
        )
        await self.db.commit()

        return {
            "id": sid,
            "period_type": period_type,
            "period_label": period_label,
            **task_metrics,
            **brain_metrics,
            **cost_metrics,
            "growth_score": growth_score,
            **deltas,
        }

    async def _task_metrics(self, start: str, end: str) -> dict:
        rows = await self.db.fetchall(
            """SELECT outcome, COUNT(*) as cnt FROM episode
               WHERE completed_at >= ? AND completed_at < (? || 'T23:59:59Z')
               GROUP BY outcome""",
            (start, end),
        )
        counts = {"SUCCESS": 0, "PARTIAL": 0, "FAILURE": 0, "ABORTED": 0}
        for r in rows:
            counts[r["outcome"]] = r["cnt"]
        total = sum(counts.values())
        success_rate = counts["SUCCESS"] / total if total > 0 else 0.0
        return {
            "total_episodes": total,
            "success": counts["SUCCESS"],
            "partial": counts["PARTIAL"],
            "failure": counts["FAILURE"] + counts["ABORTED"],
            "success_rate": success_rate,
        }

    async def _brain_metrics(self, start: str, end: str) -> dict:
        all_h = await self.db.fetchall("SELECT confidence, status FROM heuristic")
        confidences = [r["confidence"] for r in all_h]
        status_counts = {"ACTIVE": 0, "CANDIDATE": 0, "DEPRECATED": 0, "REVERTED": 0}
        for r in all_h:
            status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

        promoted = await self.db.fetchone(
            """SELECT COUNT(*) as cnt FROM heuristic
               WHERE promoted_at >= ? AND promoted_at < (? || 'T23:59:59Z')""",
            (start, end),
        )
        reverted = await self.db.fetchone(
            """SELECT COUNT(*) as cnt FROM heuristic
               WHERE deprecated_at >= ? AND deprecated_at < (? || 'T23:59:59Z')
               AND status = 'REVERTED'""",
            (start, end),
        )

        sorted_conf = sorted(confidences) if confidences else [0.0]
        return {
            "total_lessons": len(all_h),
            "active": status_counts["ACTIVE"],
            "candidate": status_counts["CANDIDATE"],
            "promoted": promoted["cnt"] if promoted else 0,
            "reverted": reverted["cnt"] if reverted else 0,
            "avg_confidence": statistics.mean(sorted_conf),
            "p50_confidence": sorted_conf[len(sorted_conf) // 2],
            "p90_confidence": sorted_conf[int(len(sorted_conf) * 0.9)],
        }

    async def _cost_metrics(self, start: str, end: str) -> dict:
        row = await self.db.fetchone(
            """SELECT COALESCE(SUM(cost_inr), 0) as total,
                      COUNT(*) as cnt
               FROM cost_receipt
               WHERE timestamp >= ? AND timestamp < (? || 'T23:59:59Z')""",
            (start, end),
        )
        total_cost = row["total"] if row else 0.0

        task_row = await self.db.fetchone(
            """SELECT COUNT(*) as cnt FROM episode
               WHERE completed_at >= ? AND completed_at < (? || 'T23:59:59Z')""",
            (start, end),
        )
        task_count = task_row["cnt"] if task_row else 0

        success_row = await self.db.fetchone(
            """SELECT COUNT(*) as cnt FROM episode
               WHERE completed_at >= ? AND completed_at < (? || 'T23:59:59Z')
               AND outcome = 'SUCCESS'""",
            (start, end),
        )
        success_count = success_row["cnt"] if success_row else 0

        return {
            "total_cost": total_cost,
            "cost_per_task": total_cost / task_count if task_count > 0 else 0.0,
            "cost_per_success": total_cost / success_count if success_count > 0 else 0.0,
        }

    def _compute_growth_score(self, tasks: dict, brain: dict, costs: dict) -> float:
        score = 0.0
        score += tasks["success_rate"] * 40
        if brain["total_lessons"] > 0:
            score += min(brain["active"] / max(brain["total_lessons"], 1), 1.0) * 30
        score += min(brain["avg_confidence"], 1.0) * 20
        if costs["cost_per_task"] > 0:
            efficiency = min(1.0 / costs["cost_per_task"], 10.0) / 10.0
            score += efficiency * 10
        else:
            score += 10
        return round(min(score, 100.0), 1)

    async def _compute_deltas(
        self, period_type: str,
        task_metrics: dict, growth_score: float,
        brain_metrics: dict,
    ) -> dict:
        prev = await self.db.fetchone(
            """SELECT * FROM improvement_snapshot
               WHERE period_type = ?
               ORDER BY period_label DESC LIMIT 1""",
            (period_type,),
        )
        if not prev:
            return {}
        return {
            "delta_success_rate": task_metrics["success_rate"] - prev["success_rate"],
            "delta_growth_score": growth_score - prev["growth_score"],
            "delta_active_lessons": brain_metrics["active"] - prev["active_lessons"],
            "delta_cost_per_task": (
                task_metrics.get("cost_per_task", 0) - prev["cost_per_task"]
                if "cost_per_task" in task_metrics else None
            ),
        }

    async def list_snapshots(
        self, period_type: str = "daily", limit: int = 30,
    ) -> list[dict]:
        rows = await self.db.fetchall(
            """SELECT * FROM improvement_snapshot
               WHERE period_type = ?
               ORDER BY period_label DESC LIMIT ?""",
            (period_type, limit),
        )
        return [dict(r) for r in rows]
