from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tars.core.db import Database
from tars.genome.changelog import ChangelogManager
from tars.genome.learning_loop import LearningLoop
from tars.genome.models import (
    CostBreakdown,
    Episode,
    EvidenceDirection,
    HeuristicStatus,
    OriginType,
    Outcome,
)
from tars.genome.promotion import PromotionEngine
from tars.genome.store import GenomeStore

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"


@pytest.fixture
async def learn_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.run_migrations(MIGRATIONS_DIR)
    yield db  # type: ignore[misc]
    await db.close()


@pytest.fixture
def store(learn_db: Database) -> GenomeStore:
    return GenomeStore(learn_db)


@pytest.fixture
def changelog(learn_db: Database) -> ChangelogManager:
    return ChangelogManager(learn_db)


@pytest.fixture
def promotion(store: GenomeStore, changelog: ChangelogManager) -> PromotionEngine:
    return PromotionEngine(store, changelog)


@pytest.fixture
def learner(
    store: GenomeStore, changelog: ChangelogManager, promotion: PromotionEngine
) -> LearningLoop:
    return LearningLoop(store, changelog, promotion, router=None)


def _make_episode(
    eid: str = "", goal: str = "test task", outcome: Outcome = Outcome.SUCCESS
) -> Episode:
    now = datetime.now(UTC)
    return Episode(
        id=eid,
        goal=goal,
        outcome=outcome,
        cost_breakdown=CostBreakdown(total_inr=1.0),
        started_at=now,
        completed_at=now,
    )


@pytest.mark.asyncio
async def test_teach_creates_candidate(learner: LearningLoop, store: GenomeStore) -> None:
    hid = await learner.on_correction("always use https for API calls")
    h = await store.get_heuristic(hid)

    assert h is not None
    assert h.statement == "always use https for API calls"
    assert h.status == HeuristicStatus.CANDIDATE
    assert h.origin_type == OriginType.TAUGHT
    assert h.confidence > 0.5


@pytest.mark.asyncio
async def test_teach_with_domain(learner: LearningLoop, store: GenomeStore) -> None:
    hid = await learner.on_correction(
        "PDFs go to papers folder", domain="file-organization", tags=["pdf"]
    )
    h = await store.get_heuristic(hid)

    assert h is not None
    assert h.scope.domains == ["file-organization"]
    assert h.scope.tags == ["pdf"]


@pytest.mark.asyncio
async def test_teach_creates_changelog(learner: LearningLoop, changelog: ChangelogManager) -> None:
    hid = await learner.on_correction("test lesson")
    log = await changelog.get_log(entity_id=hid)
    assert len(log) >= 1
    assert any(e.operation.value == "CREATE" for e in log)


@pytest.mark.asyncio
async def test_episode_adds_evidence_to_applied_lessons(
    learner: LearningLoop, store: GenomeStore
) -> None:
    h = await store.insert_heuristic("existing lesson")

    ep = _make_episode(goal="applied lesson test")
    ep_id = await store.insert_episode(ep)

    ep_saved = await store.get_episode(ep_id)
    ep_with_lessons = Episode(
        id=ep_saved.id,
        goal=ep_saved.goal,
        outcome=ep_saved.outcome,
        cost_breakdown=ep_saved.cost_breakdown,
        started_at=ep_saved.started_at,
        completed_at=ep_saved.completed_at,
        lessons_applied=[h.id],
    )

    await learner.on_episode_completed(ep_with_lessons)

    evidence = await store.get_evidence_for_heuristic(h.id)
    assert len(evidence) == 1
    assert evidence[0].direction == EvidenceDirection.SUPPORTING


@pytest.mark.asyncio
async def test_failed_episode_adds_contradicting_evidence(
    learner: LearningLoop, store: GenomeStore
) -> None:
    h = await store.insert_heuristic("bad lesson")

    ep = _make_episode(goal="failed task", outcome=Outcome.FAILURE)
    ep_id = await store.insert_episode(ep)

    ep_saved = await store.get_episode(ep_id)
    ep_with_lessons = Episode(
        id=ep_saved.id,
        goal=ep_saved.goal,
        outcome=ep_saved.outcome,
        cost_breakdown=ep_saved.cost_breakdown,
        started_at=ep_saved.started_at,
        completed_at=ep_saved.completed_at,
        lessons_applied=[h.id],
    )

    await learner.on_episode_completed(ep_with_lessons)

    evidence = await store.get_evidence_for_heuristic(h.id)
    assert len(evidence) == 1
    assert evidence[0].direction == EvidenceDirection.CONTRADICTING


@pytest.mark.asyncio
async def test_full_teach_and_promote_lifecycle(
    learner: LearningLoop, store: GenomeStore, promotion: PromotionEngine
) -> None:
    hid = await learner.on_correction("always validate input")
    h = await store.get_heuristic(hid)
    assert h.status == HeuristicStatus.CANDIDATE

    for i in range(4):
        ep = _make_episode(goal=f"task {i}")
        ep_id = await store.insert_episode(ep)
        await store.add_evidence(
            heuristic_id=hid,
            episode_id=ep_id,
            direction=EvidenceDirection.SUPPORTING,
            weight=1.0,
        )

    result = await promotion.try_promote(hid)
    assert result.eligible

    h_after = await store.get_heuristic(hid)
    assert h_after.status == HeuristicStatus.ACTIVE


@pytest.mark.asyncio
async def test_no_extraction_without_router(learner: LearningLoop) -> None:
    ep = _make_episode(goal="simple task")
    ep_id = await learner.store.insert_episode(ep)
    ep_saved = await learner.store.get_episode(ep_id)

    created = await learner.on_episode_completed(ep_saved)
    assert created == []
