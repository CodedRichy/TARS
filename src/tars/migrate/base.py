from __future__ import annotations

import re
from dataclasses import dataclass, field

from tars.core.db import Database
from tars.genome.models import OriginType, Scope
from tars.genome.store import GenomeStore


@dataclass
class ImportedLesson:
    statement: str
    domain: str = "*"
    tags: list[str] = field(default_factory=lambda: ["*"])
    source: str = ""


@dataclass
class ImportResult:
    total_found: int = 0
    imported: int = 0
    duplicates: int = 0
    lessons: list[ImportedLesson] = field(default_factory=list)


def _keyword_similarity(a: str, b: str) -> float:
    words_a = set(re.findall(r"\w+", a.lower()))
    words_b = set(re.findall(r"\w+", b.lower()))
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


class BaseImporter:
    SIMILARITY_THRESHOLD = 0.8

    def __init__(self, db: Database, store: GenomeStore) -> None:
        self.db = db
        self.store = store

    async def discover(self, path: str) -> list[ImportedLesson]:
        raise NotImplementedError

    async def import_lessons(
        self, path: str, *, dry_run: bool = False,
    ) -> ImportResult:
        discovered = await self.discover(path)
        existing = await self.store.list_heuristics(limit=500)
        existing_statements = [h.statement for h in existing]

        result = ImportResult(total_found=len(discovered))

        for lesson in discovered:
            is_dup = any(
                _keyword_similarity(lesson.statement, s) >= self.SIMILARITY_THRESHOLD
                for s in existing_statements
            )
            if is_dup:
                result.duplicates += 1
                continue

            if not dry_run:
                await self.store.insert_heuristic(
                    statement=lesson.statement,
                    scope=Scope(
                        domains=[lesson.domain] if lesson.domain != "*" else ["*"],
                        tags=lesson.tags or ["*"],
                    ),
                    origin_type=OriginType.IMPORTED,
                    initial_supporting=0.3,
                )
            result.imported += 1
            result.lessons.append(lesson)
            existing_statements.append(lesson.statement)

        return result
