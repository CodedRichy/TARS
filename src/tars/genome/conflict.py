from __future__ import annotations

from dataclasses import dataclass

from tars.genome.lesson_server import _keyword_similarity
from tars.genome.models import Heuristic, HeuristicStatus
from tars.genome.store import GenomeStore


@dataclass
class TaskContextForScope:
    goal: str = ""
    domain: str = ""
    tools: list[str] | None = None
    tags: list[str] | None = None
    project: str = ""


@dataclass
class ConflictPair:
    heuristic_a: Heuristic
    heuristic_b: Heuristic
    scope_overlap: float
    semantic_similarity: float
    suggestion: str


def _scope_overlap_between(a: Heuristic, b: Heuristic) -> float:
    a_domains = set(a.scope.domains)
    b_domains = set(b.scope.domains)
    if "*" in a_domains or "*" in b_domains:
        domain_overlap = 1.0
    elif a_domains & b_domains:
        domain_overlap = len(a_domains & b_domains) / len(a_domains | b_domains)
    else:
        return 0.0

    a_tags = set(a.scope.tags)
    b_tags = set(b.scope.tags)
    if "*" in a_tags or "*" in b_tags:
        tag_overlap = 1.0
    elif a_tags & b_tags:
        tag_overlap = len(a_tags & b_tags) / len(a_tags | b_tags)
    else:
        tag_overlap = 0.0

    return (domain_overlap + tag_overlap) / 2


class ConflictDetector:
    def __init__(self, store: GenomeStore) -> None:
        self.store = store

    async def detect(self) -> list[ConflictPair]:
        active = await self.store.list_heuristics(status=HeuristicStatus.ACTIVE)
        conflicts: list[ConflictPair] = []

        for i, a in enumerate(active):
            for b in active[i + 1 :]:
                scope_ov = _scope_overlap_between(a, b)
                if scope_ov < 0.3:
                    continue

                sim = _keyword_similarity(a.statement, b.statement)
                if sim < 0.3:
                    continue

                suggestion = _suggest_resolution(a, b)
                conflicts.append(
                    ConflictPair(
                        heuristic_a=a,
                        heuristic_b=b,
                        scope_overlap=scope_ov,
                        semantic_similarity=sim,
                        suggestion=suggestion,
                    )
                )
        return conflicts


def _suggest_resolution(a: Heuristic, b: Heuristic) -> str:
    if a.confidence > b.confidence + 0.15:
        return (
            f"Consider deprecating '{b.statement[:50]}...' "
            f"(lower confidence: {b.confidence:.2f} vs {a.confidence:.2f})"
        )
    if b.confidence > a.confidence + 0.15:
        return (
            f"Consider deprecating '{a.statement[:50]}...' "
            f"(lower confidence: {a.confidence:.2f} vs {b.confidence:.2f})"
        )
    return "Narrow the scope of one or both lessons to eliminate overlap"
