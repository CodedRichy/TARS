from __future__ import annotations

import json
from dataclasses import dataclass

from tars.genome.changelog import ChangelogManager
from tars.genome.confidence import (
    PROMOTION_MIN_CONFIDENCE,
    PROMOTION_MIN_EVIDENCE,
    PROMOTION_MIN_FRESH,
)
from tars.genome.models import ChangeOperation, HeuristicStatus
from tars.genome.store import GenomeStore


@dataclass
class PromotionResult:
    eligible: bool
    reason: str
    confidence: float = 0.0


class PromotionEngine:
    def __init__(self, store: GenomeStore, changelog: ChangelogManager) -> None:
        self.store = store
        self.changelog = changelog

    async def check(self, heuristic_id: str) -> PromotionResult:
        h = await self.store.get_heuristic(heuristic_id)
        if not h:
            return PromotionResult(False, "heuristic not found")
        if h.status != HeuristicStatus.CANDIDATE:
            return PromotionResult(False, f"status is {h.status.value}, not CANDIDATE")

        total = h.supporting + h.contradicting
        if total < PROMOTION_MIN_EVIDENCE:
            return PromotionResult(
                False, f"insufficient evidence ({total:.1f}/{PROMOTION_MIN_EVIDENCE})"
            )
        if h.confidence < PROMOTION_MIN_CONFIDENCE:
            return PromotionResult(
                False,
                f"confidence too low ({h.confidence:.2f}/{PROMOTION_MIN_CONFIDENCE})",
            )

        fresh = await self.store.count_fresh_supporting(heuristic_id)
        if fresh < PROMOTION_MIN_FRESH:
            return PromotionResult(
                False,
                f"needs more fresh evidence ({fresh}/{PROMOTION_MIN_FRESH})",
            )

        return PromotionResult(True, "meets all promotion criteria", h.confidence)

    async def try_promote(self, heuristic_id: str, auto: bool = True) -> PromotionResult:
        result = await self.check(heuristic_id)
        if not result.eligible:
            return result

        h = await self.store.get_heuristic(heuristic_id)
        if not h:
            return PromotionResult(False, "heuristic not found")

        old_status = h.status.value
        await self.store.update_heuristic_status(heuristic_id, HeuristicStatus.ACTIVE)

        updated = await self.store.get_heuristic(heuristic_id)
        snapshot = json.loads(updated.model_dump_json()) if updated else {}

        await self.changelog.append(
            entity_type="HEURISTIC",
            entity_id=heuristic_id,
            operation=ChangeOperation.STATUS_CHANGE,
            field_changes={"status": {"old": old_status, "new": "ACTIVE"}},
            reason="auto-promotion" if auto else "user-approved",
            snapshot=snapshot,
        )
        return result

    async def force_promote(self, heuristic_id: str) -> bool:
        h = await self.store.get_heuristic(heuristic_id)
        if not h or h.status != HeuristicStatus.CANDIDATE:
            return False

        await self.store.update_heuristic_status(heuristic_id, HeuristicStatus.ACTIVE)
        updated = await self.store.get_heuristic(heuristic_id)
        snapshot = json.loads(updated.model_dump_json()) if updated else {}

        await self.changelog.append(
            entity_type="HEURISTIC",
            entity_id=heuristic_id,
            operation=ChangeOperation.STATUS_CHANGE,
            field_changes={"status": {"old": "CANDIDATE", "new": "ACTIVE"}},
            reason="user-approved (forced)",
            snapshot=snapshot,
        )
        return True

    async def check_all_candidates(self) -> list[str]:
        candidates = await self.store.list_heuristics(status=HeuristicStatus.CANDIDATE)
        promoted = []
        for h in candidates:
            result = await self.try_promote(h.id)
            if result.eligible:
                promoted.append(h.id)
        return promoted
