from __future__ import annotations

import json
from pathlib import Path

import pytest

from tars.core.db import Database
from tars.genome.store import GenomeStore
from tars.migrate.base import _keyword_similarity
from tars.migrate.hermes import HermesImporter
from tars.migrate.openclaw import OpenClawImporter


@pytest.fixture
async def migrate_db(tmp_data_dir: Path) -> Database:
    db = Database(tmp_data_dir / "tars.db")
    await db.connect()
    migrations_dir = Path(__file__).parent.parent.parent / "src" / "tars" / "migrations"
    await db.run_migrations(migrations_dir)
    yield db  # type: ignore[misc]
    await db.close()


@pytest.fixture
async def store(migrate_db: Database) -> GenomeStore:
    return GenomeStore(migrate_db)


class TestKeywordSimilarity:
    def test_identical(self) -> None:
        assert _keyword_similarity("always test code", "always test code") == 1.0

    def test_similar(self) -> None:
        sim = _keyword_similarity(
            "always run tests before commit",
            "always run tests before committing",
        )
        assert sim > 0.6

    def test_different(self) -> None:
        sim = _keyword_similarity("use python for scripts", "deploy with docker")
        assert sim < 0.3

    def test_empty(self) -> None:
        assert _keyword_similarity("", "test") == 0.0


class TestHermesImporter:
    @pytest.fixture
    def hermes_dir(self, tmp_path: Path) -> Path:
        root = tmp_path / ".hermes"
        root.mkdir()

        memories = root / "memories"
        memories.mkdir()
        (memories / "MEMORY.md").write_text(
            "# Memories\n"
            "- Always validate user input before processing\n"
            "- Use descriptive variable names in Python code\n"
            "- short\n",
            encoding="utf-8",
        )

        user_file = root / "USER.md"
        user_file.write_text(
            "# User Preferences\n"
            "- Prefers concise explanations over verbose ones\n",
            encoding="utf-8",
        )

        skills = root / "skills"
        skills.mkdir()
        (skills / "testing.md").write_text(
            "# Testing Skill\n"
            "description: Run unit tests with pytest\n"
            "- Always run pytest with verbose flag for better output\n"
            "- Use fixtures for database setup and teardown operations\n",
            encoding="utf-8",
        )

        return root

    @pytest.mark.asyncio
    async def test_discover(
        self, migrate_db: Database, store: GenomeStore, hermes_dir: Path,
    ) -> None:
        importer = HermesImporter(migrate_db, store)
        lessons = await importer.discover(str(hermes_dir))
        assert len(lessons) >= 4
        sources = {lesson.source for lesson in lessons}
        assert any("memory" in s for s in sources)
        assert any("user" in s for s in sources)
        assert any("skill" in s for s in sources)

    @pytest.mark.asyncio
    async def test_import(
        self, migrate_db: Database, store: GenomeStore, hermes_dir: Path,
    ) -> None:
        importer = HermesImporter(migrate_db, store)
        result = await importer.import_lessons(str(hermes_dir))
        assert result.imported > 0
        assert result.total_found > 0

        heuristics = await store.list_heuristics()
        assert len(heuristics) == result.imported

    @pytest.mark.asyncio
    async def test_dry_run(
        self, migrate_db: Database, store: GenomeStore, hermes_dir: Path,
    ) -> None:
        importer = HermesImporter(migrate_db, store)
        result = await importer.import_lessons(str(hermes_dir), dry_run=True)
        assert result.imported > 0

        heuristics = await store.list_heuristics()
        assert len(heuristics) == 0

    @pytest.mark.asyncio
    async def test_dedup(
        self, migrate_db: Database, store: GenomeStore, hermes_dir: Path,
    ) -> None:
        importer = HermesImporter(migrate_db, store)
        await importer.import_lessons(str(hermes_dir))
        await store.list_heuristics()

        result2 = await importer.import_lessons(str(hermes_dir))
        assert result2.duplicates > 0
        assert result2.imported == 0

    @pytest.mark.asyncio
    async def test_empty_dir(
        self, migrate_db: Database, store: GenomeStore, tmp_path: Path,
    ) -> None:
        empty = tmp_path / "empty_hermes"
        empty.mkdir()
        importer = HermesImporter(migrate_db, store)
        result = await importer.import_lessons(str(empty))
        assert result.total_found == 0


class TestOpenClawImporter:
    @pytest.fixture
    def openclaw_dir(self, tmp_path: Path) -> Path:
        root = tmp_path / ".openclaw"
        root.mkdir()

        memory = root / "memory"
        memory.mkdir()
        (memory / "notes.json").write_text(
            json.dumps([
                {"content": "Always check error return values in Go code"},
                {"content": "Use context.Context for cancellation propagation"},
                {"text": "short"},
            ]),
            encoding="utf-8",
        )

        skills = root / "skills"
        skills.mkdir()
        (skills / "docker.json").write_text(
            json.dumps({
                "description": "Build and manage Docker containers for deployment",
                "steps": [
                    "Always use multi-stage builds to reduce image size",
                    "Pin base image versions for reproducible builds",
                    "short",
                ],
            }),
            encoding="utf-8",
        )

        return root

    @pytest.mark.asyncio
    async def test_discover(
        self, migrate_db: Database, store: GenomeStore, openclaw_dir: Path,
    ) -> None:
        importer = OpenClawImporter(migrate_db, store)
        lessons = await importer.discover(str(openclaw_dir))
        assert len(lessons) >= 3

    @pytest.mark.asyncio
    async def test_import(
        self, migrate_db: Database, store: GenomeStore, openclaw_dir: Path,
    ) -> None:
        importer = OpenClawImporter(migrate_db, store)
        result = await importer.import_lessons(str(openclaw_dir))
        assert result.imported > 0
        assert result.total_found > 0

    @pytest.mark.asyncio
    async def test_malformed_json(
        self, migrate_db: Database, store: GenomeStore, tmp_path: Path,
    ) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        memory = root / "memory"
        memory.mkdir()
        (memory / "bad.json").write_text("not json", encoding="utf-8")

        importer = OpenClawImporter(migrate_db, store)
        lessons = await importer.discover(str(root))
        assert lessons == []
