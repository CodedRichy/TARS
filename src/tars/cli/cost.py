from __future__ import annotations

import asyncio

import typer
from rich.table import Table

from tars.cli.theme import budget_bar, console
from tars.core.config import load_config
from tars.core.db import Database
from tars.router.budget import BudgetTracker

cost_app = typer.Typer(name="cost", help="View spending and budget status.")


@cost_app.callback(invoke_without_command=True)
def cost_today(ctx: typer.Context) -> None:
    """Show today's spending summary."""
    if ctx.invoked_subcommand is not None:
        return

    async def _run() -> None:
        cfg = load_config()
        async with Database(cfg.db_path) as db:
            await db.run_migrations(cfg.migrations_dir)
            tracker = BudgetTracker(db, cfg.budget.daily_limit_inr)
            summary = await tracker.get_daily_summary()

            spent = summary["spent_inr"]
            limit = summary["limit_inr"]
            bar = budget_bar(spent, limit, width=25)

            console.print()
            console.print(f"  [bold]Today[/bold] [dim]({summary['date']})[/dim]")
            console.print(f"  {bar}")
            console.print(f"  [dim]{summary['count']} API calls[/dim]")

            rows = await db.fetchall(
                """SELECT tier, model, COUNT(*) as calls,
                          SUM(total_tokens) as tokens,
                          SUM(cost_inr) as cost
                   FROM cost_receipt
                   WHERE timestamp LIKE ?
                   GROUP BY tier, model
                   ORDER BY cost DESC""",
                (f"{summary['date']}%",),
            )
            if rows:
                console.print()
                table = Table(
                    show_header=True,
                    header_style="bold",
                    border_style="dim",
                    show_lines=False,
                    padding=(0, 1),
                )
                table.add_column("Tier", style="cyan")
                table.add_column("Model")
                table.add_column("Calls", justify="right")
                table.add_column("Tokens", justify="right", style="dim")
                table.add_column("Cost", justify="right", style="bold")
                for r in rows:
                    table.add_row(
                        r["tier"],
                        r["model"],
                        str(r["calls"]),
                        f"{r['tokens']:,}",
                        f"Rs{r['cost']:.4f}",
                    )
                console.print(table)
            console.print()

    asyncio.run(_run())


@cost_app.command()
def month() -> None:
    """Show this month's spending summary."""

    async def _run() -> None:
        cfg = load_config()
        async with Database(cfg.db_path) as db:
            await db.run_migrations(cfg.migrations_dir)
            tracker = BudgetTracker(db, cfg.budget.daily_limit_inr)
            summary = await tracker.get_monthly_summary()

            console.print()
            console.print(f"  [bold]Month[/bold] [dim]{summary['month']}[/dim]")
            console.print(f"  Total:  [bold]Rs{summary['total_inr']:.4f}[/bold]")
            console.print(f"  Calls:  {summary['receipt_count']}")
            console.print(f"  Active: {summary['days']} days")
            console.print()

    asyncio.run(_run())
