from __future__ import annotations

from tars.core.db import Database
from tars.curves.renderer import sparkline, trend_arrow
from tars.curves.snapshot import SnapshotCollector


class ImprovementDigest:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.collector = SnapshotCollector(db)

    async def weekly_digest(self) -> str:
        snapshots = await self.collector.list_snapshots("daily", limit=7)
        if not snapshots:
            return "No data yet. Complete tasks to start tracking improvement."

        snapshots = sorted(snapshots, key=lambda s: s["period_label"])
        latest = snapshots[-1]

        rates = [s.get("success_rate", 0) for s in snapshots]
        scores = [s.get("growth_score", 0) for s in snapshots]

        delta_rate = rates[-1] - rates[0] if len(rates) > 1 else 0
        delta_score = scores[-1] - scores[0] if len(scores) > 1 else 0

        lines = [
            "TARS Weekly Improvement Digest",
            "=" * 35,
            "",
            (
                f"  Success: {sparkline(rates, 14)}"
                f"  {rates[-1]:.0%}"
                f" ({trend_arrow(delta_rate)} {delta_rate*100:+.1f}pp)"
            ),
            (
                f"  Growth:  {sparkline(scores, 14)}"
                f"  {scores[-1]:.0f}/100"
                f" ({trend_arrow(delta_score)} {delta_score:+.1f})"
            ),
            "",
            f"  Episodes this week: {sum(s.get('total_episodes', 0) for s in snapshots)}",
            f"  Lessons active: {latest.get('active_lessons', 0)}",
            f"  Cost this week: ₹{sum(s.get('total_cost_inr', 0) for s in snapshots):.2f}",
        ]

        milestones = await self._detect_milestones(latest)
        if milestones:
            lines.append("")
            lines.append("  Milestones:")
            for m in milestones:
                lines.append(f"    * {m}")

        return "\n".join(lines)

    async def _detect_milestones(self, latest: dict) -> list[str]:
        milestones = []

        if latest.get("active_lessons", 0) == 1:
            milestones.append("First lesson promoted!")

        if latest.get("total_episodes", 0) >= 10:
            total = await self.db.fetchone("SELECT COUNT(*) as cnt FROM episode")
            if total and total["cnt"] >= 10 and total["cnt"] < 15:
                milestones.append("10 episodes completed!")

        if latest.get("success_rate", 0) >= 0.9 and latest.get("total_episodes", 0) >= 5:
            milestones.append("90%+ success rate achieved!")

        if latest.get("growth_score", 0) >= 80:
            milestones.append("Growth score above 80!")

        return milestones
