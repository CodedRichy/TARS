from __future__ import annotations

from pathlib import Path

import pytest

from tars.core.db import Database
from tars.gateway.action_ledger import ActionLedger

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"


@pytest.fixture
async def ledger_db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    await db.connect()
    await db.run_migrations(MIGRATIONS_DIR)
    yield db  # type: ignore[misc]
    await db.close()


@pytest.fixture
def ledger(ledger_db: Database) -> ActionLedger:
    return ActionLedger(ledger_db)


@pytest.mark.asyncio
async def test_append_returns_hash(ledger: ActionLedger) -> None:
    h = await ledger.append(session_id="sess1", tool="shell", action="ls /tmp")
    assert len(h) == 64


@pytest.mark.asyncio
async def test_chain_hashes_differ(ledger: ActionLedger) -> None:
    h1 = await ledger.append(session_id="s1", tool="shell", action="ls")
    h2 = await ledger.append(session_id="s1", tool="shell", action="pwd")
    assert h1 != h2


@pytest.mark.asyncio
async def test_verify_chain(ledger: ActionLedger) -> None:
    await ledger.append(session_id="s1", tool="shell", action="ls")
    await ledger.append(session_id="s1", tool="shell", action="pwd")
    await ledger.append(session_id="s1", tool="read_file", action="/tmp/x")

    valid, count = await ledger.verify_chain()
    assert valid
    assert count == 3


@pytest.mark.asyncio
async def test_get_session_actions(ledger: ActionLedger) -> None:
    await ledger.append(session_id="s1", tool="shell", action="ls")
    await ledger.append(session_id="s2", tool="shell", action="pwd")
    await ledger.append(session_id="s1", tool="shell", action="cat")

    actions = await ledger.get_session_actions("s1")
    assert len(actions) == 2
    assert all(a["session_id"] == "s1" for a in actions)


@pytest.mark.asyncio
async def test_append_with_plan_step(ledger: ActionLedger) -> None:
    await ledger.append(
        session_id="s1",
        tool="shell",
        action="ls /tmp",
        plan_step="1",
        result="OK",
    )
    actions = await ledger.get_session_actions("s1")
    assert actions[0]["plan_step"] == "1"
    assert actions[0]["result"] == "OK"
