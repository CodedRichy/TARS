from __future__ import annotations

import sys

from rich.console import Console
from rich.theme import Theme

TARS_THEME = Theme(
    {
        "tars.accent": "bold cyan",
        "tars.success": "bold green",
        "tars.warn": "bold yellow",
        "tars.error": "bold red",
        "tars.dim": "dim white",
        "tars.brain": "bold magenta",
        "tars.cost": "bold yellow",
        "tars.active": "bold green",
        "tars.candidate": "bold yellow",
        "tars.deprecated": "dim",
        "tars.reverted": "strike red",
        "tars.bar.low": "green",
        "tars.bar.mid": "yellow",
        "tars.bar.high": "red",
        "tars.header": "bold bright_white on rgb(30,30,50)",
    }
)

_force_terminal = sys.platform == "win32"
console = Console(theme=TARS_THEME, force_terminal=_force_terminal)

BANNER = """\
[bold cyan]
  _____ _   ___ ___
 |_   _/_\\ | _ \\ __|
   | |/ _ \\|   / _|
   |_/_/ \\_\\_|_\\___|[/bold cyan]"""

TAGLINE = "[dim]The first AI agent with a brain you can watch grow.[/dim]"

STATUS_STYLE = {
    "CANDIDATE": "tars.candidate",
    "ACTIVE": "tars.active",
    "DEPRECATED": "tars.deprecated",
    "REVERTED": "tars.reverted",
}

STATUS_ICON = {
    "CANDIDATE": "~",
    "ACTIVE": "*",
    "DEPRECATED": ".",
    "REVERTED": "x",
}

OUTCOME_ICON = {
    "SUCCESS": "[green]OK[/green]",
    "PARTIAL": "[yellow]PARTIAL[/yellow]",
    "FAILURE": "[red]FAIL[/red]",
    "ABORTED": "[red]ABORT[/red]",
}

STEP_ICON = {
    "success": "[green]OK[/green]",
    "failed": "[red]FAIL[/red]",
    "permission_denied": "[yellow]DENIED[/yellow]",
    "skipped": "[dim]SKIP[/dim]",
}


def confidence_bar(value: float, width: int = 15) -> str:
    filled = int(value * width)
    empty = width - filled
    if value >= 0.7:
        color = "green"
    elif value >= 0.45:
        color = "yellow"
    else:
        color = "red"
    bar = f"[{color}]{'#' * filled}{'-' * empty}[/{color}]"
    return f"{bar} {value:.0%}"


def budget_bar(spent: float, limit: float, width: int = 20) -> str:
    pct = (spent / limit * 100) if limit > 0 else 0
    filled = int(width * min(pct, 100) / 100)
    if pct < 60:
        color = "green"
    elif pct < 80:
        color = "yellow"
    else:
        color = "red"
    bar_str = f"[{color}]{'#' * filled}{'-' * (width - filled)}[/{color}]"
    return f"{bar_str} Rs{spent:.2f}/Rs{limit:.0f} ({pct:.0f}%)"


def print_banner() -> None:
    console.print(BANNER)
    console.print(f"  {TAGLINE}")
    console.print()
