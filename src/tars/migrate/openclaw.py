from __future__ import annotations

import json
from pathlib import Path

from tars.core.db import Database
from tars.genome.store import GenomeStore
from tars.migrate.base import BaseImporter, ImportedLesson


class OpenClawImporter(BaseImporter):
    """Import memories from OpenClaw (~/.openclaw/)."""

    def __init__(self, db: Database, store: GenomeStore) -> None:
        super().__init__(db, store)

    async def discover(self, path: str) -> list[ImportedLesson]:
        root = Path(path)
        lessons: list[ImportedLesson] = []

        memory_dir = root / "memory"
        if memory_dir.exists():
            for json_file in memory_dir.glob("*.json"):
                lessons.extend(self._parse_memory_json(json_file))

        skills_dir = root / "skills"
        if skills_dir.exists():
            for skill_file in skills_dir.glob("*.json"):
                lessons.extend(self._parse_skill_json(skill_file))

        return lessons

    def _parse_memory_json(self, path: Path) -> list[ImportedLesson]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

        lessons = []
        if isinstance(data, list):
            for item in data:
                stmt = self._extract_statement(item)
                if stmt:
                    lessons.append(ImportedLesson(
                        statement=stmt,
                        source=f"openclaw:memory:{path.stem}",
                    ))
        elif isinstance(data, dict):
            stmt = self._extract_statement(data)
            if stmt:
                lessons.append(ImportedLesson(
                    statement=stmt,
                    source=f"openclaw:memory:{path.stem}",
                ))
        return lessons

    def _parse_skill_json(self, path: Path) -> list[ImportedLesson]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

        lessons = []
        name = path.stem

        if isinstance(data, dict):
            desc = data.get("description", "")
            if desc and len(desc) > 10:
                lessons.append(ImportedLesson(
                    statement=f"Skill '{name}': {desc[:400]}",
                    source=f"openclaw:skill:{name}",
                    domain=name,
                ))

            steps = data.get("steps", [])
            if isinstance(steps, list):
                for step in steps:
                    if isinstance(step, str) and len(step) > 20:
                        lessons.append(ImportedLesson(
                            statement=step[:500],
                            source=f"openclaw:skill:{name}",
                            domain=name,
                        ))

        return lessons

    def _extract_statement(self, item: dict | str) -> str | None:
        if isinstance(item, str):
            return item[:500] if len(item) > 10 else None

        if isinstance(item, dict):
            for key in ("content", "text", "statement", "memory", "note"):
                val = item.get(key, "")
                if isinstance(val, str) and len(val) > 10:
                    return val[:500]
        return None
