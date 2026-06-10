from __future__ import annotations

import asyncio

import typer
from rich.panel import Panel

from tars.cli.theme import confidence_bar, console
from tars.core.config import load_config
from tars.core.db import Database
from tars.genome.store import GenomeStore
from tars.review.sunday_review import SundayReview


def review(days: int = typer.Option(7, "--days", "-d", help="Days to review")) -> None:
    """Generate a self-review report."""

    async def _run() -> None:
        cfg = load_config()
        async with Database(cfg.db_path) as db:
            await db.run_migrations(cfg.migrations_dir)
            store = GenomeStore(db)
            reviewer = SundayReview(store)
            report = await reviewer.generate(days=days)

            sr = report.success_rate
            sr_color = "green" if sr >= 0.7 else "yellow" if sr >= 0.4 else "red"
            growth_color = "green" if report.growth_score > 0 else "red"

            content = (
                f"[bold]Task Performance[/bold]\n"
                f"  Total: {report.episodes_total}  "
                f"[{sr_color}]{report.episodes_success} success[/{sr_color}]  "
                f"{report.episodes_partial} partial  "
                f"{report.episodes_failed} failed\n"
                f"  Success rate: [{sr_color}]{sr:.0%}[/{sr_color}]\n\n"
                f"[bold]Brain Growth[/bold]\n"
                f"  [green]+{report.lessons_created}[/green] new  "
                f"[cyan]^{report.lessons_promoted}[/cyan] promoted  "
                f"[red]-{report.lessons_deprecated}[/red] deprecated\n"
                f"  Growth score: "
                f"[{growth_color}]{report.growth_score:+.1f}[/{growth_color}]\n\n"
                f"[bold]Cost[/bold]  Rs{report.total_cost_inr:.2f}"
            )

            start_str = report.period_start.strftime("%Y-%m-%d")
            end_str = report.period_end.strftime("%Y-%m-%d")

            console.print()
            console.print(
                Panel(
                    content,
                    title=(
                        f"[tars.accent]* Self-Review[/tars.accent]  "
                        f"[dim]{start_str} -> {end_str}[/dim]"
                    ),
                    border_style="cyan",
                    padding=(1, 2),
                )
            )

            if report.top_lessons:
                console.print("  [bold]Top Lessons[/bold]")
                for tl in report.top_lessons[:5]:
                    bar = confidence_bar(tl["confidence"], width=8)
                    console.print(f"    {bar}  {tl['statement']}")
            console.print()

    asyncio.run(_run())
