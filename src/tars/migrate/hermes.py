from __future__ import annotations

import re
from pathlib import Path

from tars.core.db import Database
from tars.genome.store import GenomeStore
from tars.migrate.base import BaseImporter, ImportedLesson


class HermesImporter(BaseImporter):
    """Import memories and skills from Hermes Agent (~/.hermes/)."""

    def __init__(self, db: Database, store: GenomeStore) -> None:
        super().__init__(db, store)

    async def discover(self, path: str) -> list[ImportedLesson]:
        root = Path(path)
        lessons: list[ImportedLesson] = []

        memories_dir = root / "memories"
        if memories_dir.exists():
            for md_file in memories_dir.glob("*.md"):
                lessons.extend(self._parse_memory_file(md_file))

        user_file = root / "USER.md"
        if user_file.exists():
            lessons.extend(self._parse_user_file(user_file))

        skills_dir = root / "skills"
        if skills_dir.exists():
            for skill_file in skills_dir.glob("*.md"):
                lessons.extend(self._parse_skill_file(skill_file))

        return lessons

    def _parse_memory_file(self, path: Path) -> list[ImportedLesson]:
        content = path.read_text(encoding="utf-8", errors="replace")
        lessons = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("- "):
                line = line[2:]
            if len(line) > 20 and not line.startswith("```"):
                lessons.append(ImportedLesson(
                    statement=line[:500],
                    source=f"hermes:memory:{path.stem}",
                ))
        return lessons

    def _parse_user_file(self, path: Path) -> list[ImportedLesson]:
        content = path.read_text(encoding="utf-8", errors="replace")
        lessons = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("- "):
                line = line[2:]
            if len(line) > 20:
                lessons.append(ImportedLesson(
                    statement=line[:500],
                    source="hermes:user",
                    domain="user-preferences",
                ))
        return lessons

    def _parse_skill_file(self, path: Path) -> list[ImportedLesson]:
        content = path.read_text(encoding="utf-8", errors="replace")
        name = path.stem
        lessons = []

        description_match = re.search(
            r"(?:^|\n)(?:description|purpose):\s*(.+)", content, re.IGNORECASE,
        )
        if description_match:
            lessons.append(ImportedLesson(
                statement=f"Skill '{name}': {description_match.group(1).strip()[:400]}",
                source=f"hermes:skill:{name}",
                domain=name,
            ))

        for match in re.finditer(r"(?:^|\n)[-*]\s+(.{20,200})", content):
            stmt = match.group(1).strip()
            if not stmt.startswith("```"):
                lessons.append(ImportedLesson(
                    statement=stmt,
                    source=f"hermes:skill:{name}",
                    domain=name,
                ))

        return lessons
