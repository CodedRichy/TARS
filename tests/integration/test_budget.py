from __future__ import annotations

from pathlib import Path

import pytest

from tars.core.db import Database
from tars.router.budget import BudgetExceededError, BudgetTracker
from tars.router.receipt import Receipt

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"


@pytest.fixture
async def budget_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.run_migrations(MIGRATIONS_DIR)
    yield db  # type: ignore[misc]
    await db.close()


@pytest.fixture
def tracker(budget_db: Database) -> BudgetTracker:
    return BudgetTracker(budget_db, daily_limit_inr=10.0)


@pytest.mark.asyncio
async def test_initial_budget_empty(tracker: BudgetTracker) -> None:
    spent, limit = await tracker.check_budget()
    assert spent == 0.0
    assert limit == 10.0


@pytest.mark.asyncio
async def test_can_spend_initially(tracker: BudgetTracker) -> None:
    assert await tracker.can_spend(5.0)


@pytest.mark.asyncio
async def test_record_and_track_spend(tracker: BudgetTracker) -> None:
    r = Receipt(tier="cheap", provider="openai", model="gpt-4.1-mini", cost_inr=3.0)
    new_spent = await tracker.record_spend(r)
    assert new_spent == 3.0

    spent, _ = await tracker.check_budget()
    assert spent == 3.0


@pytest.mark.asyncio
async def test_multiple_spends_accumulate(tracker: BudgetTracker) -> None:
    r1 = Receipt(tier="cheap", provider="openai", model="gpt-4.1-mini", cost_inr=3.0)
    r2 = Receipt(tier="frontier", provider="anthropic", model="sonnet", cost_inr=4.0)
    await tracker.record_spend(r1)
    await tracker.record_spend(r2)

    spent, _ = await tracker.check_budget()
    assert spent == 7.0


@pytest.mark.asyncio
async def test_cannot_spend_over_limit(tracker: BudgetTracker) -> None:
    r = Receipt(tier="frontier", provider="anthropic", model="sonnet", cost_inr=9.0)
    await tracker.record_spend(r)
    assert not await tracker.can_spend(2.0)


@pytest.mark.asyncio
async def test_daily_summary(tracker: BudgetTracker) -> None:
    r = Receipt(tier="cheap", provider="openai", model="gpt-4.1-mini", cost_inr=2.5)
    await tracker.record_spend(r)

    summary = await tracker.get_daily_summary()
    assert summary["spent_inr"] == 2.5
    assert summary["count"] == 1


@pytest.mark.asyncio
async def test_monthly_summary_empty(tracker: BudgetTracker) -> None:
    summary = await tracker.get_monthly_summary()
    assert summary["total_inr"] == 0.0
    assert summary["receipt_count"] == 0


@pytest.mark.asyncio
async def test_budget_exceeded_exception() -> None:
    exc = BudgetExceededError(55.0, 50.0)
    assert exc.spent == 55.0
    assert exc.limit == 50.0
    assert "₹55.00" in str(exc)
