from __future__ import annotations

from pathlib import Path

import pytest

from tars.agent.context_compiler import CompiledContext, ContextCompiler
from tars.core.db import Database
from tars.genome.lesson_server import LessonServer
from tars.genome.models import HeuristicStatus, Scope
from tars.genome.store import GenomeStore

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"


@pytest.fixture
async def ctx_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.run_migrations(MIGRATIONS_DIR)
    yield db  # type: ignore[misc]
    await db.close()


@pytest.fixture
def store(ctx_db: Database) -> GenomeStore:
    return GenomeStore(ctx_db)


@pytest.fixture
def compiler(store: GenomeStore) -> ContextCompiler:
    return ContextCompiler(LessonServer(store))


def test_empty_context_render() -> None:
    ctx = CompiledContext(goal="do something")
    rendered = ctx.render()
    assert "## Goal" in rendered
    assert "do something" in rendered


def test_context_with_tools() -> None:
    ctx = CompiledContext(goal="test", tools_available=["shell", "read_file"])
    rendered = ctx.render()
    assert "shell" in rendered
    assert "read_file" in rendered


@pytest.mark.asyncio
async def test_compiler_includes_lessons(store: GenomeStore, compiler: ContextCompiler) -> None:
    h = await store.insert_heuristic(
        "always check file permissions",
        scope=Scope(domains=["filesystem"]),
    )
    await store.update_heuristic_status(h.id, HeuristicStatus.ACTIVE)

    ctx = await compiler.compile(
        goal="read a config file",
        domain="filesystem",
    )
    assert len(ctx.lessons) == 1
    rendered = ctx.render()
    assert "always check file permissions" in rendered


@pytest.mark.asyncio
async def test_compiler_no_lessons_wrong_domain(
    store: GenomeStore, compiler: ContextCompiler
) -> None:
    h = await store.insert_heuristic(
        "always check file permissions",
        scope=Scope(domains=["filesystem"]),
    )
    await store.update_heuristic_status(h.id, HeuristicStatus.ACTIVE)

    ctx = await compiler.compile(
        goal="send an email",
        domain="email",
    )
    assert len(ctx.lessons) == 0
