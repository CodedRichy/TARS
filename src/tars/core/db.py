from __future__ import annotations

import hashlib
from pathlib import Path

import aiosqlite


class Database:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self._path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.execute("PRAGMA busy_timeout=5000")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    async def execute(self, sql: str, params: tuple | list | None = None) -> aiosqlite.Cursor:
        return await self.conn.execute(sql, params or [])

    async def executemany(self, sql: str, params: list) -> aiosqlite.Cursor:
        return await self.conn.executemany(sql, params)

    async def fetchone(self, sql: str, params: tuple | list | None = None) -> aiosqlite.Row | None:
        cursor = await self.execute(sql, params)
        return await cursor.fetchone()

    async def fetchall(self, sql: str, params: tuple | list | None = None) -> list[aiosqlite.Row]:
        cursor = await self.execute(sql, params)
        return await cursor.fetchall()

    async def commit(self) -> None:
        await self.conn.commit()

    async def run_migrations(self, migrations_dir: Path) -> int:
        await self.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
        """)
        await self.commit()

        applied_rows = await self.fetchall("SELECT filename FROM _migrations ORDER BY id")
        applied = {row["filename"] for row in applied_rows}

        if not migrations_dir.exists():
            return 0

        migration_files = sorted(migrations_dir.glob("*.sql"))
        count = 0

        for mf in migration_files:
            if mf.name in applied:
                continue
            sql = mf.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            await self.conn.executescript(sql)
            await self.execute(
                "INSERT INTO _migrations (filename, checksum) VALUES (?, ?)",
                (mf.name, checksum),
            )
            await self.commit()
            count += 1

        return count

    async def __aenter__(self) -> Database:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
