from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tars.core.db import Database
from tars.genome.changelog import ChangelogManager
from tars.genome.confidence import compute_confidence
from tars.genome.conflict import ConflictDetector
from tars.genome.lesson_server import LessonServer, TaskContext
from tars.genome.models import (
    CostBreakdown,
    Episode,
    EvidenceDirection,
    FailureModel,
    HeuristicStatus,
    OriginType,
    Outcome,
    Scope,
)
from tars.genome.promotion import PromotionEngine
from tars.genome.store import GenomeStore
from tars.genome.versioning import BrainVersioning

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"


@pytest.fixture
async def genome_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.run_migrations(MIGRATIONS_DIR)
    yield db  # type: ignore[misc]
    await db.close()


@pytest.fixture
def store(genome_db: Database) -> GenomeStore:
    return GenomeStore(genome_db)


@pytest.fixture
def changelog(genome_db: Database) -> ChangelogManager:
    return ChangelogManager(genome_db)


@pytest.fixture
def versioning(store: GenomeStore, changelog: ChangelogManager) -> BrainVersioning:
    return BrainVersioning(store, changelog)


@pytest.fixture
def promotion(store: GenomeStore, changelog: ChangelogManager) -> PromotionEngine:
    return PromotionEngine(store, changelog)


def _make_episode(goal: str = "test task", outcome: Outcome = Outcome.SUCCESS) -> Episode:
    now = datetime.now(UTC)
    return Episode(
        id="",
        goal=goal,
        context_features={"domain": "testing"},
        outcome=outcome,
        cost_breakdown=CostBreakdown(total_inr=1.0),
        started_at=now,
        completed_at=now,
    )


@pytest.mark.asyncio
async def test_insert_and_retrieve_episode(store: GenomeStore) -> None:
    ep = _make_episode()
    eid = await store.insert_episode(ep)
    assert eid

    retrieved = await store.get_episode(eid)
    assert retrieved is not None
    assert retrieved.goal == "test task"
    assert retrieved.outcome == Outcome.SUCCESS


@pytest.mark.asyncio
async def test_insert_and_retrieve_heuristic(store: GenomeStore) -> None:
    h = await store.insert_heuristic(
        statement="always test your code",
        scope=Scope(domains=["testing"]),
        origin_type=OriginType.TAUGHT,
        initial_supporting=1,
    )
    assert h.id
    assert h.status == HeuristicStatus.CANDIDATE
    assert h.confidence == compute_confidence(1, 0)

    retrieved = await store.get_heuristic(h.id)
    assert retrieved is not None
    assert retrieved.statement == "always test your code"
    assert retrieved.scope.domains == ["testing"]


@pytest.mark.asyncio
async def test_evidence_updates_confidence(store: GenomeStore) -> None:
    ep = _make_episode()
    eid = await store.insert_episode(ep)

    h = await store.insert_heuristic("test lesson")
    await store.add_evidence(h.id, eid, EvidenceDirection.SUPPORTING, weight=1.0)

    updated = await store.get_heuristic(h.id)
    assert updated is not None
    assert updated.confidence > 0.5
    assert updated.supporting == 1.0


@pytest.mark.asyncio
async def test_origin_evidence_weight(store: GenomeStore) -> None:
    ep = _make_episode()
    eid = await store.insert_episode(ep)

    h = await store.insert_heuristic("test lesson")
    await store.add_evidence(h.id, eid, EvidenceDirection.SUPPORTING, weight=0.3, is_origin=True)

    updated = await store.get_heuristic(h.id)
    assert updated is not None
    assert updated.supporting == 0.3


@pytest.mark.asyncio
async def test_promotion_requires_evidence(store: GenomeStore, promotion: PromotionEngine) -> None:
    h = await store.insert_heuristic("test lesson")
    result = await promotion.check(h.id)
    assert not result.eligible
    assert "insufficient evidence" in result.reason


@pytest.mark.asyncio
async def test_full_promotion_lifecycle(store: GenomeStore, promotion: PromotionEngine) -> None:
    h = await store.insert_heuristic("test lesson")

    for i in range(4):
        ep = _make_episode(goal=f"task {i}")
        eid = await store.insert_episode(ep)
        await store.add_evidence(
            h.id, eid, EvidenceDirection.SUPPORTING, weight=1.0, is_origin=i == 0
        )

    result = await promotion.try_promote(h.id)
    assert result.eligible

    updated = await store.get_heuristic(h.id)
    assert updated is not None
    assert updated.status == HeuristicStatus.ACTIVE


@pytest.mark.asyncio
async def test_revert_lesson(
    store: GenomeStore, versioning: BrainVersioning, changelog: ChangelogManager
) -> None:
    h = await store.insert_heuristic("lesson to revert")
    ok = await versioning.revert_lesson(h.id)
    assert ok

    updated = await store.get_heuristic(h.id)
    assert updated is not None
    assert updated.status == HeuristicStatus.REVERTED

    evidence = await store.get_evidence_for_heuristic(h.id)
    for e in evidence:
        assert e.weight == 0.0

    log = await changelog.get_log(entity_id=h.id)
    assert any(e.operation.value == "REVERT" for e in log)


@pytest.mark.asyncio
async def test_changelog_hash_chain(store: GenomeStore, changelog: ChangelogManager) -> None:
    from tars.genome.models import ChangeOperation

    await changelog.append("HEURISTIC", "test1", ChangeOperation.CREATE)
    await changelog.append("HEURISTIC", "test2", ChangeOperation.CREATE)
    await changelog.append("HEURISTIC", "test1", ChangeOperation.UPDATE)

    valid, count = await changelog.verify_chain()
    assert valid
    assert count == 3


@pytest.mark.asyncio
async def test_lesson_server_scope_matching(store: GenomeStore) -> None:
    h = await store.insert_heuristic(
        "PDFs go to papers folder",
        scope=Scope(domains=["file-organization"], tags=["pdf"]),
    )
    await store.update_heuristic_status(h.id, HeuristicStatus.ACTIVE)

    server = LessonServer(store)
    ctx = TaskContext(goal="organize my downloads", domain="file-organization", tags=["pdf"])
    results = await server.serve(ctx)
    assert len(results) == 1
    assert results[0].heuristic.id == h.id


@pytest.mark.asyncio
async def test_lesson_server_no_match_wrong_domain(store: GenomeStore) -> None:
    h = await store.insert_heuristic(
        "PDFs go to papers folder",
        scope=Scope(domains=["file-organization"]),
    )
    await store.update_heuristic_status(h.id, HeuristicStatus.ACTIVE)

    server = LessonServer(store)
    ctx = TaskContext(goal="fix the database", domain="database-admin")
    results = await server.serve(ctx)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_conflict_detection(store: GenomeStore) -> None:
    h1 = await store.insert_heuristic(
        "always use force push for git",
        scope=Scope(domains=["git"], tags=["push"]),
    )
    h2 = await store.insert_heuristic(
        "never use force push for git",
        scope=Scope(domains=["git"], tags=["push"]),
    )
    await store.update_heuristic_status(h1.id, HeuristicStatus.ACTIVE)
    await store.update_heuristic_status(h2.id, HeuristicStatus.ACTIVE)

    detector = ConflictDetector(store)
    conflicts = await detector.detect()
    assert len(conflicts) == 1
    assert {conflicts[0].heuristic_a.id, conflicts[0].heuristic_b.id} == {h1.id, h2.id}


@pytest.mark.asyncio
async def test_failure_model_crud(store: GenomeStore) -> None:
    fm = FailureModel(
        id="",
        signature="missing DB migration",
        root_cause="forgot to run migrate",
        recovery_path=["run migrations", "retry"],
        scope=Scope(domains=["database"]),
        source_episodes=["ep1"],
    )
    fid = await store.insert_failure_model(fm)
    assert fid

    models = await store.list_active_failure_models()
    assert len(models) == 1
    assert models[0].signature == "missing DB migration"


@pytest.mark.asyncio
async def test_brain_diff(
    store: GenomeStore, versioning: BrainVersioning, changelog: ChangelogManager
) -> None:
    from tars.genome.models import ChangeOperation

    before = datetime.now(UTC)

    h = await store.insert_heuristic("new lesson")
    await changelog.append(
        "HEURISTIC", h.id, ChangeOperation.CREATE, snapshot={"statement": h.statement}
    )

    diff = await versioning.brain_diff(before)
    assert len(diff.new_entities) == 1
    assert diff.new_entities[0].entity_id == h.id
