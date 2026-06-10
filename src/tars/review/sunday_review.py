from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from tars.genome.confidence import evidence_strength
from tars.genome.models import HeuristicStatus, Outcome
from tars.genome.store import GenomeStore
from tars.router.budget import BudgetTracker


@dataclass
class WeeklyReport:
    period_start: datetime
    period_end: datetime
    episodes_total: int = 0
    episodes_success: int = 0
    episodes_partial: int = 0
    episodes_failed: int = 0
    lessons_created: int = 0
    lessons_promoted: int = 0
    lessons_deprecated: int = 0
    total_cost_inr: float = 0.0
    top_lessons: list[dict] = field(default_factory=list)
    growth_score: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.episodes_total == 0:
            return 0.0
        return self.episodes_success / self.episodes_total

    def render_text(self) -> str:
        lines = [
            "## TARS Sunday Self-Review",
            f"Period: {self.period_start:%Y-%m-%d} → {self.period_end:%Y-%m-%d}",
            "",
            "### Task Performance",
            f"  Total tasks: {self.episodes_total}",
            f"  Success: {self.episodes_success} ({self.success_rate:.0%})",
            f"  Partial: {self.episodes_partial}",
            f"  Failed:  {self.episodes_failed}",
            "",
            "### Brain Growth",
            f"  New lessons:    {self.lessons_created}",
            f"  Promoted:       {self.lessons_promoted}",
            f"  Deprecated:     {self.lessons_deprecated}",
            f"  Growth score:   {self.growth_score:.1f}",
            "",
            f"### Cost: ₹{self.total_cost_inr:.2f}",
        ]

        if self.top_lessons:
            lines.append("")
            lines.append("### Top Active Lessons")
            for tl in self.top_lessons[:5]:
                lines.append(f"  [{tl['confidence']:.0%}] {tl['statement']}")

        return "\n".join(lines)


class SundayReview:
    def __init__(self, store: GenomeStore, budget: BudgetTracker | None = None) -> None:
        self.store = store
        self.budget = budget

    async def generate(self, days: int = 7) -> WeeklyReport:
        now = datetime.now(UTC)
        start = now - timedelta(days=days)

        episodes = await self.store.list_episodes(since=start)

        report = WeeklyReport(period_start=start, period_end=now)
        report.episodes_total = len(episodes)
        report.episodes_success = sum(1 for e in episodes if e.outcome == Outcome.SUCCESS)
        report.episodes_partial = sum(1 for e in episodes if e.outcome == Outcome.PARTIAL)
        report.episodes_failed = sum(1 for e in episodes if e.outcome == Outcome.FAILURE)

        report.total_cost_inr = sum(e.cost_breakdown.total_inr for e in episodes)

        all_heuristics = await self.store.list_heuristics()

        start_str = str(start)
        report.lessons_promoted = sum(
            1
            for h in all_heuristics
            if h.status == HeuristicStatus.ACTIVE
            and h.promoted_at
            and str(h.promoted_at) >= start_str
        )
        report.lessons_deprecated = sum(
            1
            for h in all_heuristics
            if h.status == HeuristicStatus.DEPRECATED
            and h.deprecated_at
            and str(h.deprecated_at) >= start_str
        )
        report.lessons_created = sum(
            1 for h in all_heuristics if h.created_at and str(h.created_at) >= start_str
        )

        active = [h for h in all_heuristics if h.status == HeuristicStatus.ACTIVE]
        active.sort(key=lambda h: h.confidence, reverse=True)
        report.top_lessons = [
            {
                "id": h.id[:12],
                "statement": h.statement,
                "confidence": h.confidence,
                "evidence": evidence_strength(h.supporting, h.contradicting),
            }
            for h in active[:5]
        ]

        report.growth_score = (
            report.lessons_created * 1.0
            + report.lessons_promoted * 3.0
            - report.lessons_deprecated * 1.0
            + report.episodes_success * 0.5
            - report.episodes_failed * 0.5
        )

        return report
