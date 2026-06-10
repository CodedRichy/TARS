from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tars.core.db import Database
from tars.genome.models import CostBreakdown, Episode, HeuristicStatus, Outcome
from tars.genome.store import GenomeStore
from tars.review.sunday_review import SundayReview, WeeklyReport

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"


@pytest.fixture
async def review_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.run_migrations(MIGRATIONS_DIR)
    yield db  # type: ignore[misc]
    await db.close()


@pytest.fixture
def store(review_db: Database) -> GenomeStore:
    return GenomeStore(review_db)


def test_empty_report_render() -> None:
    r = WeeklyReport(
        period_start=datetime.now(UTC),
        period_end=datetime.now(UTC),
    )
    text = r.render_text()
    assert "Sunday Self-Review" in text
    assert "Total tasks: 0" in text


def test_success_rate_zero_tasks() -> None:
    r = WeeklyReport(period_start=datetime.now(UTC), period_end=datetime.now(UTC))
    assert r.success_rate == 0.0


def test_success_rate_calculation() -> None:
    r = WeeklyReport(
        period_start=datetime.now(UTC),
        period_end=datetime.now(UTC),
        episodes_total=10,
        episodes_success=7,
    )
    assert r.success_rate == 0.7


@pytest.mark.asyncio
async def test_generate_empty_report(store: GenomeStore) -> None:
    reviewer = SundayReview(store)
    report = await reviewer.generate()
    assert report.episodes_total == 0
    assert report.growth_score == 0.0


@pytest.mark.asyncio
async def test_generate_with_episodes(store: GenomeStore) -> None:
    now = datetime.now(UTC)
    for i in range(3):
        ep = Episode(
            id="",
            goal=f"task {i}",
            outcome=Outcome.SUCCESS,
            cost_breakdown=CostBreakdown(total_inr=1.0),
            started_at=now,
            completed_at=now,
        )
        await store.insert_episode(ep)

    ep_fail = Episode(
        id="",
        goal="failed task",
        outcome=Outcome.FAILURE,
        cost_breakdown=CostBreakdown(total_inr=2.0),
        started_at=now,
        completed_at=now,
    )
    await store.insert_episode(ep_fail)

    reviewer = SundayReview(store)
    report = await reviewer.generate()
    assert report.episodes_total == 4
    assert report.episodes_success == 3
    assert report.episodes_failed == 1
    assert report.total_cost_inr == 5.0


@pytest.mark.asyncio
async def test_generate_includes_top_lessons(store: GenomeStore) -> None:
    h = await store.insert_heuristic("top lesson")
    await store.update_heuristic_status(h.id, HeuristicStatus.ACTIVE)

    reviewer = SundayReview(store)
    report = await reviewer.generate()
    assert len(report.top_lessons) == 1
    assert report.top_lessons[0]["statement"] == "top lesson"
