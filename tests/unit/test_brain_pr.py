from __future__ import annotations

from pathlib import Path

import pytest

from tars.cli.brain_review import BrainReviewEngine
from tars.core.db import Database
from tars.genome.models import HeuristicStatus
from tars.genome.store import GenomeStore


@pytest.fixture
async def pr_db(tmp_data_dir: Path) -> Database:
    db = Database(tmp_data_dir / "tars.db")
    await db.connect()
    migrations_dir = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"
    await db.run_migrations(migrations_dir)
    yield db  # type: ignore[misc]
    await db.close()


@pytest.fixture
async def store(pr_db: Database) -> GenomeStore:
    return GenomeStore(pr_db)


@pytest.fixture
async def engine(pr_db: Database, store: GenomeStore) -> BrainReviewEngine:
    return BrainReviewEngine(pr_db, store)


class TestBrainReviewEngine:
    @pytest.mark.asyncio
    async def test_create_pr(self, engine: BrainReviewEngine, store: GenomeStore) -> None:
        h = await store.insert_heuristic("test lesson")
        pr_num = await engine.create_pr(h.id)
        assert pr_num > 0

    @pytest.mark.asyncio
    async def test_list_pending_empty(self, engine: BrainReviewEngine) -> None:
        pending = await engine.list_pending()
        assert pending == []

    @pytest.mark.asyncio
    async def test_list_pending(self, engine: BrainReviewEngine, store: GenomeStore) -> None:
        h = await store.insert_heuristic("test lesson")
        await engine.create_pr(h.id)
        pending = await engine.list_pending()
        assert len(pending) == 1
        assert pending[0]["statement"] == "test lesson"

    @pytest.mark.asyncio
    async def test_get_pr(self, engine: BrainReviewEngine, store: GenomeStore) -> None:
        h = await store.insert_heuristic("test lesson")
        pr_num = await engine.create_pr(h.id)
        pr = await engine.get_pr(pr_num)
        assert pr is not None
        assert pr["status"] == "PENDING"
        assert pr["heuristic_id"] == h.id

    @pytest.mark.asyncio
    async def test_get_pr_not_found(self, engine: BrainReviewEngine) -> None:
        pr = await engine.get_pr(999)
        assert pr is None

    @pytest.mark.asyncio
    async def test_approve(self, engine: BrainReviewEngine, store: GenomeStore) -> None:
        h = await store.insert_heuristic("test lesson")
        pr_num = await engine.create_pr(h.id)
        ok = await engine.approve(pr_num)
        assert ok

        pr = await engine.get_pr(pr_num)
        assert pr["status"] == "APPROVED"
        assert pr["resolved_by"] == "user"

        updated = await store.get_heuristic(h.id)
        assert updated is not None
        assert updated.status == HeuristicStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_approve_nonexistent(self, engine: BrainReviewEngine) -> None:
        ok = await engine.approve(999)
        assert not ok

    @pytest.mark.asyncio
    async def test_reject(self, engine: BrainReviewEngine, store: GenomeStore) -> None:
        h = await store.insert_heuristic("bad lesson")
        pr_num = await engine.create_pr(h.id)
        ok = await engine.reject(pr_num, reason="not useful")
        assert ok

        pr = await engine.get_pr(pr_num)
        assert pr["status"] == "REJECTED"
        assert pr["reason"] == "not useful"

    @pytest.mark.asyncio
    async def test_reject_already_approved(
        self, engine: BrainReviewEngine, store: GenomeStore,
    ) -> None:
        h = await store.insert_heuristic("test")
        pr_num = await engine.create_pr(h.id)
        await engine.approve(pr_num)
        ok = await engine.reject(pr_num)
        assert not ok

    @pytest.mark.asyncio
    async def test_auto_approve_eligible(
        self, engine: BrainReviewEngine, store: GenomeStore,
    ) -> None:
        h1 = await store.insert_heuristic(
            "high confidence lesson",
            initial_supporting=8,
        )
        h2 = await store.insert_heuristic(
            "low confidence lesson",
            initial_supporting=1,
        )
        await engine.create_pr(h1.id)
        await engine.create_pr(h2.id)

        approved = await engine.auto_approve_eligible(
            min_confidence=0.85, min_evidence=5,
        )
        assert len(approved) == 1

        pr1 = await engine.get_pr(approved[0])
        assert pr1["status"] == "APPROVED"
        assert pr1["resolved_by"] == "auto"

    @pytest.mark.asyncio
    async def test_auto_approve_none_eligible(
        self, engine: BrainReviewEngine, store: GenomeStore,
    ) -> None:
        h = await store.insert_heuristic("low confidence", initial_supporting=1)
        await engine.create_pr(h.id)
        approved = await engine.auto_approve_eligible()
        assert approved == []

    @pytest.mark.asyncio
    async def test_double_approve_fails(
        self, engine: BrainReviewEngine, store: GenomeStore,
    ) -> None:
        h = await store.insert_heuristic("test")
        pr_num = await engine.create_pr(h.id)
        ok1 = await engine.approve(pr_num)
        ok2 = await engine.approve(pr_num)
        assert ok1
        assert not ok2
