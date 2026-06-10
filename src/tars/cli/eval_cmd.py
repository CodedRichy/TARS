from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.panel import Panel

from tars.cli.theme import console
from tars.core.config import load_config
from tars.core.db import Database
from tars.eval.harness import EvalHarness, load_suite
from tars.router.model_router import ModelRouter
from tars.tools.filesystem import ListFilesTool, ReadFileTool, WriteFileTool
from tars.tools.shell import ShellTool


def eval_cmd(
    suite: Path = typer.Argument(help="Path to eval suite JSON file"),
) -> None:
    """Run A/B eval comparing task success with/without lessons."""

    async def _run() -> None:
        cfg = load_config()
        async with Database(cfg.db_path) as db:
            await db.run_migrations(cfg.migrations_dir)
            router = ModelRouter(cfg, db)
            tools = {
                "shell": ShellTool(),
                "read_file": ReadFileTool(),
                "write_file": WriteFileTool(),
                "list_files": ListFilesTool(),
            }

            tasks = load_suite(suite)
            console.print(f"\n  [tars.accent]* Running {len(tasks)} eval tasks...[/tars.accent]\n")

            with console.status("[tars.accent]Evaluating...[/tars.accent]", spinner="dots"):
                harness = EvalHarness(router, db, tools)
                summary = await harness.run_suite(tasks)

            sig = summary.p_value <= 0.05
            sig_color = "green" if sig else "dim"
            sig_text = "SIGNIFICANT" if sig else "not significant"

            lift_color = "green" if summary.lift > 0 else "red" if summary.lift < 0 else "dim"

            content = (
                f"[bold]With lessons:[/bold]    "
                f"{summary.with_lessons_success}/{summary.total} success\n"
                f"[bold]Without lessons:[/bold] "
                f"{summary.without_lessons_success}/{summary.total} success"
                f"\n\n"
                f"[bold]Lift:[/bold] [{lift_color}]{summary.lift:+.1%}"
                f"[/{lift_color}]"
                f"  ({summary.lift_pct:+.1f}%)\n"
                f"[bold]p-value:[/bold] {summary.p_value}\n"
                f"[bold]Result:[/bold] [{sig_color}]{sig_text}[/{sig_color}]"
            )

            console.print(
                Panel(
                    content,
                    title=("[tars.accent]* A/B Eval Results[/tars.accent]"),
                    border_style="cyan",
                    padding=(1, 2),
                )
            )
            console.print()

    asyncio.run(_run())
