from __future__ import annotations

from datetime import UTC, datetime

from tars.core.db import Database
from tars.router.receipt import Receipt


class BudgetExceededError(Exception):
    def __init__(self, spent: float, limit: float) -> None:
        self.spent = spent
        self.limit = limit
        super().__init__(f"Daily budget exceeded: ₹{spent:.2f}/₹{limit:.2f}")


class BudgetTracker:
    def __init__(self, db: Database, daily_limit_inr: float = 50.0) -> None:
        self.db = db
        self.daily_limit_inr = daily_limit_inr

    async def check_budget(self) -> tuple[float, float]:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        row = await self.db.fetchone("SELECT spent_inr FROM daily_budget WHERE date = ?", (today,))
        spent = row["spent_inr"] if row else 0.0
        return spent, self.daily_limit_inr

    async def can_spend(self, estimated_cost: float = 0.0) -> bool:
        spent, limit = await self.check_budget()
        return (spent + estimated_cost) <= limit

    async def record_spend(self, receipt: Receipt) -> float:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        existing = await self.db.fetchone(
            "SELECT spent_inr, receipt_count FROM daily_budget WHERE date = ?", (today,)
        )

        if existing:
            new_spent = existing["spent_inr"] + receipt.cost_inr
            new_count = existing["receipt_count"] + 1
            await self.db.execute(
                "UPDATE daily_budget SET spent_inr = ?, receipt_count = ? WHERE date = ?",
                (new_spent, new_count, today),
            )
        else:
            new_spent = receipt.cost_inr
            await self.db.execute(
                """INSERT INTO daily_budget (date, spent_inr, limit_inr, receipt_count)
                   VALUES (?, ?, ?, 1)""",
                (today, receipt.cost_inr, self.daily_limit_inr),
            )

        await self.db.execute(
            """INSERT INTO cost_receipt
               (id, timestamp, session_id, episode_id, tier, provider, model,
                prompt_tokens, completion_tokens, total_tokens, cost_inr,
                latency_ms, task_class, stakes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            receipt.to_row(),
        )
        await self.db.commit()
        return new_spent

    async def get_daily_summary(self, date: str | None = None) -> dict:
        date = date or datetime.now(UTC).strftime("%Y-%m-%d")
        row = await self.db.fetchone("SELECT * FROM daily_budget WHERE date = ?", (date,))
        if not row:
            return {"date": date, "spent_inr": 0.0, "limit_inr": self.daily_limit_inr, "count": 0}
        return {
            "date": date,
            "spent_inr": row["spent_inr"],
            "limit_inr": row["limit_inr"],
            "count": row["receipt_count"],
        }

    async def get_monthly_summary(self, year: int | None = None, month: int | None = None) -> dict:
        now = datetime.now(UTC)
        year = year or now.year
        month = month or now.month
        prefix = f"{year}-{month:02d}"
        rows = await self.db.fetchall(
            "SELECT * FROM daily_budget WHERE date LIKE ? ORDER BY date",
            (f"{prefix}%",),
        )
        total = sum(r["spent_inr"] for r in rows)
        count = sum(r["receipt_count"] for r in rows)
        return {
            "month": prefix,
            "total_inr": round(total, 4),
            "receipt_count": count,
            "days": len(rows),
        }
