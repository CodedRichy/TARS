from __future__ import annotations

from dataclasses import dataclass

from tars.genome.models import FailureModel, Heuristic, HeuristicStatus, Scope
from tars.genome.store import GenomeStore


@dataclass
class ScoredHeuristic:
    heuristic: Heuristic
    score: float


@dataclass
class TaskContext:
    goal: str
    domain: str = ""
    tools: list[str] | None = None
    tags: list[str] | None = None
    project: str = ""


def _scope_overlaps(scope: Scope, ctx: TaskContext) -> float:
    domain_score = 0.0
    if "*" in scope.domains:
        domain_score = 0.8
    elif ctx.domain and ctx.domain in scope.domains:
        domain_score = 1.0
    elif ctx.domain and "*" not in scope.domains:
        return 0.0

    tag_score = 0.0
    if "*" in scope.tags:
        tag_score = 0.5
    elif ctx.tags:
        overlap = set(scope.tags) & set(ctx.tags)
        if overlap:
            tag_score = len(overlap) / max(len(scope.tags), len(ctx.tags))

    tool_score = 0.0
    if "*" in scope.tools:
        tool_score = 0.5
    elif ctx.tools:
        overlap = set(scope.tools) & set(ctx.tools)
        if overlap:
            tool_score = len(overlap) / max(len(scope.tools), len(ctx.tools))

    return (domain_score * 0.5) + (tag_score * 0.3) + (tool_score * 0.2)


def _keyword_similarity(statement: str, goal: str) -> float:
    s_words = set(statement.lower().split())
    g_words = set(goal.lower().split())
    stop = {"the", "a", "an", "is", "are", "to", "for", "in", "on", "of", "and", "or", "it"}
    s_words -= stop
    g_words -= stop
    if not s_words or not g_words:
        return 0.0
    overlap = s_words & g_words
    return len(overlap) / max(len(s_words), len(g_words))


class LessonServer:
    def __init__(self, store: GenomeStore) -> None:
        self.store = store

    async def serve(self, ctx: TaskContext, top_k: int = 5) -> list[ScoredHeuristic]:
        active = await self.store.list_heuristics(status=HeuristicStatus.ACTIVE)
        scored: list[ScoredHeuristic] = []

        for h in active:
            scope_score = _scope_overlaps(h.scope, ctx)
            if scope_score < 0.1:
                continue
            keyword_score = _keyword_similarity(h.statement, ctx.goal)
            confidence_score = h.confidence
            total = (0.4 * scope_score) + (0.3 * keyword_score) + (0.3 * confidence_score)
            scored.append(ScoredHeuristic(heuristic=h, score=total))

        scored.sort(key=lambda x: x.score, reverse=True)

        for sh in scored[:top_k]:
            await self.store.mark_applied(sh.heuristic.id)

        return scored[:top_k]

    async def check_failure_models(self, ctx: TaskContext) -> list[FailureModel]:
        models = await self.store.list_active_failure_models()
        matches: list[FailureModel] = []
        for fm in models:
            scope_score = _scope_overlaps(fm.scope, ctx)
            keyword_score = _keyword_similarity(fm.signature, ctx.goal)
            if scope_score > 0.3 or keyword_score > 0.3:
                matches.append(fm)
        return matches
