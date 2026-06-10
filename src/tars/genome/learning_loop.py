from __future__ import annotations

import re
from dataclasses import dataclass

from tars.genome.changelog import ChangelogManager
from tars.genome.models import (
    ChangeOperation,
    Episode,
    EvidenceDirection,
    OriginType,
    Outcome,
    Scope,
)
from tars.genome.promotion import PromotionEngine
from tars.genome.store import GenomeStore
from tars.router.model_router import ModelRouter, Stakes, TaskClass

EXTRACT_SYSTEM_PROMPT = """\
You are TARS's learning engine. Given a completed task episode, extract \
candidate lessons (heuristics) that could help in future similar tasks.

Rules:
- Only extract lessons that are generalizable, not task-specific
- Each lesson should be a clear, actionable statement
- Include scope information: what domain/tools/tags this applies to
- If the task failed, extract what went wrong as a lesson

Respond with ONLY a JSON array:
[
  {
    "statement": "clear actionable heuristic",
    "domains": ["relevant-domain"],
    "tags": ["relevant-tags"],
    "confidence_hint": "high|medium|low"
  }
]

If no lessons can be extracted, respond with: []"""


@dataclass
class ExtractedLesson:
    statement: str
    domains: list[str]
    tags: list[str]
    confidence_hint: str = "medium"


CORRECTION_PATTERNS = [
    r"(?:actually|no),?\s+((?:always|never|don't|do)\s+.+)",
    r"(?:remember|note):\s+(.+)",
    r"(?:from now on|going forward),?\s+(.+)",
    r"(?:the rule is|the pattern is)\s+(.+)",
    r"(?:you should|always|never)\s+(.+)",
]


def detect_correction(message: str) -> str | None:
    lower = message.lower().strip()
    for pattern in CORRECTION_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            return match.group(1).strip()
    return None


class LearningLoop:
    def __init__(
        self,
        store: GenomeStore,
        changelog: ChangelogManager,
        promotion: PromotionEngine,
        router: ModelRouter | None = None,
    ) -> None:
        self.store = store
        self.changelog = changelog
        self.promotion = promotion
        self.router = router

    async def on_episode_completed(self, episode: Episode) -> list[str]:
        created_ids: list[str] = []

        if self.router:
            lessons = await self._extract_from_episode(episode)
            for lesson in lessons:
                heuristic = await self.store.insert_heuristic(
                    statement=lesson.statement,
                    scope=Scope(
                        domains=lesson.domains or ["*"],
                        tags=lesson.tags or ["*"],
                    ),
                    origin_type=OriginType.EXTRACTED,
                    origin_episode_id=episode.id,
                    initial_supporting=0.3 if episode.outcome == Outcome.SUCCESS else 0,
                    initial_contradicting=0.3 if episode.outcome == Outcome.FAILURE else 0,
                )

                await self.store.add_evidence(
                    heuristic_id=heuristic.id,
                    episode_id=episode.id,
                    direction=(
                        EvidenceDirection.SUPPORTING
                        if episode.outcome in (Outcome.SUCCESS, Outcome.PARTIAL)
                        else EvidenceDirection.CONTRADICTING
                    ),
                    weight=0.3,
                    is_origin=True,
                    reasoning=f"extracted from episode {episode.id[:12]}",
                )

                await self.changelog.append(
                    entity_type="HEURISTIC",
                    entity_id=heuristic.id,
                    operation=ChangeOperation.CREATE,
                    reason=f"extracted from episode {episode.id[:12]}",
                    snapshot={"statement": heuristic.statement},
                )
                created_ids.append(heuristic.id)

        for lesson_id in episode.lessons_applied:
            direction = (
                EvidenceDirection.SUPPORTING
                if episode.outcome in (Outcome.SUCCESS, Outcome.PARTIAL)
                else EvidenceDirection.CONTRADICTING
            )
            await self.store.add_evidence(
                heuristic_id=lesson_id,
                episode_id=episode.id,
                direction=direction,
                weight=1.0,
                reasoning=f"applied in episode {episode.id[:12]}, outcome={episode.outcome.value}",
            )

        await self.promotion.check_all_candidates()

        return created_ids

    async def on_correction(
        self,
        statement: str,
        domain: str = "",
        tags: list[str] | None = None,
        episode_id: str | None = None,
    ) -> str:
        heuristic = await self.store.insert_heuristic(
            statement=statement,
            scope=Scope(
                domains=[domain] if domain else ["*"],
                tags=tags or ["*"],
            ),
            origin_type=OriginType.TAUGHT,
            origin_episode_id=episode_id,
            initial_supporting=1,
        )

        if episode_id:
            await self.store.add_evidence(
                heuristic_id=heuristic.id,
                episode_id=episode_id,
                direction=EvidenceDirection.SUPPORTING,
                weight=0.3,
                is_origin=True,
                reasoning="taught by user",
            )

        await self.changelog.append(
            entity_type="HEURISTIC",
            entity_id=heuristic.id,
            operation=ChangeOperation.CREATE,
            reason="user correction/teaching",
            snapshot={"statement": heuristic.statement},
        )

        return heuristic.id

    async def _extract_from_episode(self, episode: Episode) -> list[ExtractedLesson]:
        if not self.router:
            return []

        summary = (
            f"Goal: {episode.goal}\n"
            f"Outcome: {episode.outcome.value}\n"
            f"Context: {episode.context_features}\n"
            f"Steps: {len(episode.action_trace)}"
        )

        if episode.outcome_detail:
            summary += f"\nDetail: {episode.outcome_detail}"

        try:
            import json

            response = await self.router.complete(
                messages=[
                    {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
                    {"role": "user", "content": summary},
                ],
                task_class=TaskClass.SIMPLE,
                stakes=Stakes.LOW,
                temperature=0.3,
                max_tokens=1024,
            )

            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]

            data = json.loads(text)
            if not isinstance(data, list):
                return []

            return [
                ExtractedLesson(
                    statement=item.get("statement", ""),
                    domains=item.get("domains", ["*"]),
                    tags=item.get("tags", ["*"]),
                    confidence_hint=item.get("confidence_hint", "medium"),
                )
                for item in data
                if item.get("statement")
            ]
        except Exception:
            return []
