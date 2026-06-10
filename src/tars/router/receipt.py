from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field
from ulid import ULID


class Receipt(BaseModel):
    id: str = Field(default_factory=lambda: str(ULID()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: str | None = None
    episode_id: str | None = None
    tier: str = ""
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_inr: float = 0.0
    latency_ms: int = 0
    task_class: str | None = None
    stakes: str | None = None

    @property
    def summary(self) -> str:
        return (
            f"{self.tier}/{self.model} — "
            f"{self.total_tokens} tok, "
            f"₹{self.cost_inr:.4f}, "
            f"{self.latency_ms}ms"
        )

    def to_row(self) -> tuple:
        return (
            self.id,
            self.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            self.session_id,
            self.episode_id,
            self.tier,
            self.provider,
            self.model,
            self.prompt_tokens,
            self.completion_tokens,
            self.total_tokens,
            self.cost_inr,
            self.latency_ms,
            self.task_class,
            self.stakes,
        )


INR_PER_USD = 85.0

COST_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    "gpt-4.1-mini": {"prompt": 0.0004, "completion": 0.0016},
    "gpt-4.1-nano": {"prompt": 0.0001, "completion": 0.0004},
    "gpt-4.1": {"prompt": 0.002, "completion": 0.008},
    "claude-sonnet-4-20250514": {"prompt": 0.003, "completion": 0.015},
    "claude-haiku-4-5-20251001": {"prompt": 0.0008, "completion": 0.004},
}


def estimate_cost_inr(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = COST_PER_1K_TOKENS.get(model, {"prompt": 0.001, "completion": 0.002})
    usd = (prompt_tokens / 1000 * rates["prompt"]) + (
        completion_tokens / 1000 * rates["completion"]
    )
    return round(usd * INR_PER_USD, 6)
