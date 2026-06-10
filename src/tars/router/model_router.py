from __future__ import annotations

import enum
from dataclasses import dataclass

from tars.core.config import TarsConfig
from tars.core.db import Database
from tars.router.budget import BudgetExceededError, BudgetTracker
from tars.router.providers import ModelResponse, call_model


class Tier(enum.StrEnum):
    LOCAL = "local"
    CHEAP = "cheap"
    FRONTIER = "frontier"


class TaskClass(enum.StrEnum):
    TRIAGE = "triage"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    CRITICAL = "critical"


class Stakes(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


ROUTING_TABLE: dict[tuple[TaskClass, Stakes], Tier] = {
    (TaskClass.TRIAGE, Stakes.LOW): Tier.LOCAL,
    (TaskClass.TRIAGE, Stakes.MEDIUM): Tier.LOCAL,
    (TaskClass.TRIAGE, Stakes.HIGH): Tier.CHEAP,
    (TaskClass.SIMPLE, Stakes.LOW): Tier.LOCAL,
    (TaskClass.SIMPLE, Stakes.MEDIUM): Tier.CHEAP,
    (TaskClass.SIMPLE, Stakes.HIGH): Tier.CHEAP,
    (TaskClass.MODERATE, Stakes.LOW): Tier.CHEAP,
    (TaskClass.MODERATE, Stakes.MEDIUM): Tier.CHEAP,
    (TaskClass.MODERATE, Stakes.HIGH): Tier.FRONTIER,
    (TaskClass.COMPLEX, Stakes.LOW): Tier.CHEAP,
    (TaskClass.COMPLEX, Stakes.MEDIUM): Tier.FRONTIER,
    (TaskClass.COMPLEX, Stakes.HIGH): Tier.FRONTIER,
    (TaskClass.CRITICAL, Stakes.LOW): Tier.FRONTIER,
    (TaskClass.CRITICAL, Stakes.MEDIUM): Tier.FRONTIER,
    (TaskClass.CRITICAL, Stakes.HIGH): Tier.FRONTIER,
}


def pick_tier(task_class: TaskClass, stakes: Stakes) -> Tier:
    return ROUTING_TABLE.get((task_class, stakes), Tier.CHEAP)


@dataclass
class TierConfig:
    provider: str
    model: str

    @property
    def is_local(self) -> bool:
        return self.provider == "ollama"


class ModelRouter:
    def __init__(self, config: TarsConfig, db: Database) -> None:
        self.config = config
        self.budget = BudgetTracker(db, config.budget.daily_limit_inr)
        self.tiers: dict[Tier, TierConfig] = {
            Tier.LOCAL: TierConfig(
                provider=config.models.local_provider,
                model=config.models.local_model,
            ),
            Tier.CHEAP: TierConfig(
                provider=config.models.cheap_provider,
                model=config.models.cheap_model,
            ),
            Tier.FRONTIER: TierConfig(
                provider=config.models.frontier_provider,
                model=config.models.frontier_model,
            ),
        }

    async def complete(
        self,
        messages: list[dict],
        task_class: TaskClass = TaskClass.MODERATE,
        stakes: Stakes = Stakes.MEDIUM,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        session_id: str | None = None,
        episode_id: str | None = None,
        tier_override: Tier | None = None,
    ) -> ModelResponse:
        tier = tier_override or pick_tier(task_class, stakes)
        tier_cfg = self.tiers[tier]

        if not tier_cfg.is_local:
            can = await self.budget.can_spend()
            if not can:
                spent, limit = await self.budget.check_budget()
                raise BudgetExceededError(spent, limit)

        response = await call_model(
            messages=messages,
            model=tier_cfg.model,
            provider=tier_cfg.provider,
            tier=tier.value,
            temperature=temperature,
            max_tokens=max_tokens,
            session_id=session_id,
            episode_id=episode_id,
            task_class=task_class.value,
            stakes=stakes.value,
        )

        if response.receipt.cost_inr > 0:
            await self.budget.record_spend(response.receipt)

        return response

    async def get_budget_status(self) -> dict:
        return await self.budget.get_daily_summary()
