from __future__ import annotations

from pathlib import Path

import pytest

from tars.core.db import Database


@pytest.mark.asyncio
async def test_connect_creates_file(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    async with Database(db_path) as db:
        assert db_path.exists()
        row = await db.fetchone("PRAGMA journal_mode")
        assert row is not None
        assert row[0] == "wal"


@pytest.mark.asyncio
async def test_migrations(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    migrations = tmp_path / "migrations"
    migrations.mkdir()

    (migrations / "001_create_test.sql").write_text(
        "CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT NOT NULL);",
        encoding="utf-8",
    )

    async with Database(db_path) as db:
        count = await db.run_migrations(migrations)
        assert count == 1

        await db.execute("INSERT INTO test_table (name) VALUES (?)", ("hello",))
        await db.commit()
        row = await db.fetchone("SELECT name FROM test_table WHERE id = 1")
        assert row is not None
        assert row["name"] == "hello"

        count_again = await db.run_migrations(migrations)
        assert count_again == 0


@pytest.mark.asyncio
async def test_migrations_ordering(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    migrations = tmp_path / "migrations"
    migrations.mkdir()

    (migrations / "001_first.sql").write_text(
        "CREATE TABLE t1 (id INTEGER PRIMARY KEY);",
        encoding="utf-8",
    )
    (migrations / "002_second.sql").write_text(
        "CREATE TABLE t2 (id INTEGER PRIMARY KEY, t1_id INTEGER REFERENCES t1(id));",
        encoding="utf-8",
    )

    async with Database(db_path) as db:
        count = await db.run_migrations(migrations)
        assert count == 2

        rows = await db.fetchall("SELECT filename FROM _migrations ORDER BY id")
        assert [r["filename"] for r in rows] == ["001_first.sql", "002_second.sql"]


@pytest.mark.asyncio
async def test_not_connected_raises() -> None:
    db = Database(Path("/tmp/never.db"))
    with pytest.raises(RuntimeError, match="not connected"):
        _ = db.conn
