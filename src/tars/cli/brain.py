from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import typer
from rich.panel import Panel
from rich.table import Table

from tars.cli.theme import (
    STATUS_ICON,
    STATUS_STYLE,
    confidence_bar,
    console,
)
from tars.core.config import load_config
from tars.core.db import Database
from tars.genome.changelog import ChangelogManager
from tars.genome.confidence import evidence_strength
from tars.genome.conflict import ConflictDetector
from tars.genome.promotion import PromotionEngine
from tars.genome.store import GenomeStore
from tars.genome.versioning import BrainVersioning

brain_app = typer.Typer(name="brain", help="Inspect and manage the TARS brain.")


async def _get_components() -> tuple[
    Database, GenomeStore, ChangelogManager, BrainVersioning, PromotionEngine
]:
    cfg = load_config()
    db = Database(cfg.db_path)
    await db.connect()
    await db.run_migrations(cfg.migrations_dir)
    store = GenomeStore(db)
    cl = ChangelogManager(db)
    ver = BrainVersioning(store, cl)
    promo = PromotionEngine(store, cl)
    return db, store, cl, ver, promo


@brain_app.callback(invoke_without_command=True)
def brain_dashboard(ctx: typer.Context) -> None:
    """Show the brain dashboard -- all lessons with status and confidence."""
    if ctx.invoked_subcommand is not None:
        return

    async def _run() -> None:
        db, store, cl, ver, promo = await _get_components()
        try:
            lessons = await store.list_heuristics()
            if not lessons:
                console.print(
                    Panel(
                        "[tars.dim]Brain is empty.\n\n"
                        "Teach me something:[/tars.dim]\n"
                        '  [cyan]tars teach "always validate user input"[/cyan]',
                        title="[tars.brain]~ TARS Brain[/tars.brain]",
                        border_style="magenta",
                        padding=(1, 2),
                    )
                )
                return

            active = sum(1 for h in lessons if h.status.value == "ACTIVE")
            candidates = sum(1 for h in lessons if h.status.value == "CANDIDATE")
            total = len(lessons)

            header = (
                f"[bold]{total}[/bold] lessons  "
                f"[tars.active]* {active} active[/tars.active]  "
                f"[tars.candidate]~ {candidates} candidates[/tars.candidate]"
            )

            table = Table(
                show_header=True,
                header_style="bold bright_white",
                border_style="dim",
                show_lines=False,
                padding=(0, 1),
                expand=True,
            )
            table.add_column("", width=2)
            table.add_column("Lesson", ratio=4)
            table.add_column("Confidence", ratio=2, justify="left")
            table.add_column("Evidence", justify="center", width=10)
            table.add_column("Scope", ratio=1, style="dim")

            for h in lessons:
                style = STATUS_STYLE.get(h.status.value, "white")
                icon = STATUS_ICON.get(h.status.value, "?")
                strength = evidence_strength(h.supporting, h.contradicting)
                evidence_total = h.supporting + h.contradicting
                bar = confidence_bar(h.confidence, width=10)

                evidence_display = f"{strength}"
                if evidence_total > 0:
                    evidence_display += f" ({evidence_total:.0f})"

                table.add_row(
                    f"[{style}]{icon}[/{style}]",
                    f"[{style}]{h.statement}[/{style}]",
                    bar,
                    evidence_display,
                    h.scope.summary,
                )

            console.print()
            console.print(
                Panel(
                    table,
                    title=f"[tars.brain]~ TARS Brain[/tars.brain]  {header}",
                    border_style="magenta",
                    padding=(0, 1),
                )
            )

            detector = ConflictDetector(store)
            conflicts = await detector.detect()
            if conflicts:
                console.print()
                for c in conflicts:
                    console.print(
                        f"  [tars.warn]! Conflict:[/tars.warn] "
                        f"'{c.heuristic_a.statement[:40]}..' vs "
                        f"'{c.heuristic_b.statement[:40]}..'"
                    )
                    console.print(f"    [dim]{c.suggestion}[/dim]")

            console.print()
        finally:
            await db.close()

    asyncio.run(_run())


@brain_app.command()
def log(limit: int = typer.Option(20, "--limit", "-n")) -> None:
    """Show brain changelog."""

    async def _run() -> None:
        db, store, cl, ver, promo = await _get_components()
        try:
            entries = await ver.brain_log(limit=limit)
            if not entries:
                console.print("[tars.dim]No brain history yet.[/tars.dim]")
                return

            op_icons = {
                "CREATE": "[green]+[/green]",
                "STATUS_CHANGE": "[cyan]^[/cyan]",
                "EVIDENCE_ADD": "[blue]+[/blue]",
                "REVERT": "[red]x[/red]",
                "UPDATE": "[yellow]~[/yellow]",
            }

            console.print()
            for e in entries:
                ts = str(e.timestamp)[:16] if e.timestamp else "?"
                icon = op_icons.get(e.operation.value, ".")
                console.print(
                    f"  [dim]{ts}[/dim]  {icon} "
                    f"[bold]{e.operation.value.lower()}[/bold] "
                    f"[dim]{e.entity_id[:12]}[/dim]"
                )
                if e.reason:
                    console.print(f"               [dim]{e.reason}[/dim]")
                for fld, val in e.field_changes.items():
                    console.print(
                        f"               {fld}: "
                        f"[red]{val.get('old')}[/red] -> "
                        f"[green]{val.get('new')}[/green]"
                    )
            console.print()
        finally:
            await db.close()

    asyncio.run(_run())


@brain_app.command()
def diff(since: str = typer.Option("7d", "--since", "-s")) -> None:
    """Show brain changes since a time period (e.g., 7d, 30d, 2h)."""
    unit = since[-1]
    amount = int(since[:-1])
    if unit == "d":
        delta = timedelta(days=amount)
    elif unit == "h":
        delta = timedelta(hours=amount)
    else:
        console.print("[tars.error]Use format like 7d or 24h[/tars.error]")
        raise typer.Exit(1)

    target = datetime.now(UTC) - delta

    async def _run() -> None:
        db, store, cl, ver, promo = await _get_components()
        try:
            bd = await ver.brain_diff(target)
            total = len(bd.new_entities) + len(bd.changed_entities) + len(bd.reverted_entities)
            if total == 0:
                console.print(f"[tars.dim]No changes in the last {since}.[/tars.dim]")
                return

            console.print(f"\n  [bold]Brain diff[/bold] [dim](last {since})[/dim]\n")

            if bd.new_entities:
                console.print(f"  [green]+ {len(bd.new_entities)} new[/green]")
                for ed in bd.new_entities:
                    snap = ed.changes[0].snapshot if ed.changes else {}
                    stmt = snap.get("statement", ed.entity_id[:12])
                    console.print(f"    [green]+[/green] {stmt}")

            if bd.changed_entities:
                console.print(f"  [yellow]~ {len(bd.changed_entities)} modified[/yellow]")
                for ed in bd.changed_entities:
                    net = ed.net_change
                    console.print(f"    [yellow]~[/yellow] {ed.entity_id[:12]}")
                    for fld, val in net.items():
                        console.print(
                            f"      {fld}: [red]{val.get('old')}[/red]"
                            f" -> [green]{val.get('new')}[/green]"
                        )

            if bd.reverted_entities:
                console.print(f"  [red]- {len(bd.reverted_entities)} reverted[/red]")
                for ed in bd.reverted_entities:
                    console.print(f"    [red]x[/red] {ed.entity_id[:12]}")

            console.print()
        finally:
            await db.close()

    asyncio.run(_run())


@brain_app.command()
def revert(
    target: str = typer.Argument(help="Lesson ID (prefix) or date (YYYY-MM-DD) to revert"),
) -> None:
    """Revert a lesson or all changes after a date."""

    async def _run() -> None:
        db, store, cl, ver, promo = await _get_components()
        try:
            try:
                dt = datetime.fromisoformat(target).replace(tzinfo=UTC)
                ids = await ver.revert_to_date(dt)
                console.print(
                    f"  [tars.error]x Reverted {len(ids)} lesson(s) after {target}[/tars.error]"
                )
            except ValueError:
                lessons = await store.list_heuristics()
                match = [h for h in lessons if h.id.startswith(target)]
                if not match:
                    console.print(f"[tars.error]No lesson matching '{target}'[/tars.error]")
                    raise typer.Exit(1) from None
                for h in match:
                    ok = await ver.revert_lesson(h.id)
                    if ok:
                        console.print(f"  [tars.error]x[/tars.error] {h.statement}")
        finally:
            await db.close()

    asyncio.run(_run())


@brain_app.command()
def approve(
    lesson_id: str = typer.Argument(help="Lesson ID prefix to force-promote"),
) -> None:
    """Force-promote a candidate lesson to ACTIVE."""

    async def _run() -> None:
        db, store, cl, ver, promo = await _get_components()
        try:
            lessons = await store.list_heuristics()
            match = [h for h in lessons if h.id.startswith(lesson_id)]
            if not match:
                console.print(f"[tars.error]No lesson matching '{lesson_id}'[/tars.error]")
                raise typer.Exit(1)
            for h in match:
                ok = await promo.force_promote(h.id)
                if ok:
                    console.print(f"  [tars.active]* Promoted:[/tars.active] {h.statement}")
                else:
                    console.print(
                        f"  [tars.warn]Cannot promote {h.id[:12]} "
                        f"(status: {h.status.value})[/tars.warn]"
                    )
        finally:
            await db.close()

    asyncio.run(_run())


@brain_app.command(name="review")
def brain_review() -> None:
    """List pending Brain PRs for review."""
    from tars.cli.brain_review import BrainReviewEngine

    async def _run() -> None:
        db, store, cl, ver, promo = await _get_components()
        try:
            engine = BrainReviewEngine(db, store)
            pending = await engine.list_pending()
            if not pending:
                console.print("[tars.dim]No pending Brain PRs.[/tars.dim]")
                return

            table = Table(
                show_header=True,
                header_style="bold bright_white",
                border_style="dim",
            )
            table.add_column("#", width=5)
            table.add_column("Lesson", ratio=3)
            table.add_column("Confidence", ratio=1)
            table.add_column("Evidence", width=10)

            for pr in pending:
                bar = confidence_bar(pr["confidence"], width=10)
                ev = f"+{pr['supporting']:.0f} -{pr['contradicting']:.0f}"
                table.add_row(
                    str(pr["pr_number"]),
                    pr["statement"],
                    bar,
                    ev,
                )

            console.print()
            console.print(
                Panel(
                    table,
                    title="[tars.brain]~ Brain PRs[/tars.brain]",
                    border_style="magenta",
                )
            )
        finally:
            await db.close()

    asyncio.run(_run())


@brain_app.command(name="pr")
def brain_pr_action(
    pr_number: int = typer.Argument(help="Brain PR number"),
    action: str = typer.Option(
        "show", "--action", "-a", help="show|approve|reject"
    ),
    reason: str = typer.Option("", "--reason", "-r", help="Rejection reason"),
) -> None:
    """Show, approve, or reject a Brain PR."""
    from tars.cli.brain_review import BrainReviewEngine

    async def _run() -> None:
        db, store, cl, ver, promo = await _get_components()
        try:
            engine = BrainReviewEngine(db, store)

            if action == "approve":
                ok = await engine.approve(pr_number)
                if ok:
                    console.print(
                        f"  [tars.success]Approved PR #{pr_number}[/tars.success]"
                    )
                else:
                    console.print(
                        f"  [tars.error]Cannot approve #{pr_number}[/tars.error]"
                    )
                return

            if action == "reject":
                ok = await engine.reject(pr_number, reason=reason)
                if ok:
                    console.print(
                        f"  [tars.error]Rejected PR #{pr_number}[/tars.error]"
                    )
                else:
                    console.print(
                        f"  [tars.error]Cannot reject #{pr_number}[/tars.error]"
                    )
                return

            pr = await engine.get_pr(pr_number)
            if not pr:
                console.print(f"[tars.error]PR #{pr_number} not found[/tars.error]")
                raise typer.Exit(1)

            bar = confidence_bar(pr["confidence"], width=15)
            console.print()
            console.print(
                Panel(
                    f"[bold]{pr['statement']}[/bold]\n\n"
                    f"  Status: {pr['status']}\n"
                    f"  Confidence: {bar}\n"
                    f"  Evidence: +{pr['supporting']:.0f}"
                    f" -{pr['contradicting']:.0f}\n"
                    f"  Created: {pr['created_at']}",
                    title=f"[tars.brain]Brain PR #{pr_number}[/tars.brain]",
                    border_style="magenta",
                )
            )
        finally:
            await db.close()

    asyncio.run(_run())


@brain_app.command(name="auto-approve")
def brain_auto_approve(
    min_confidence: float = typer.Option(0.85, "--min-confidence"),
    min_evidence: int = typer.Option(5, "--min-evidence"),
) -> None:
    """Auto-approve Brain PRs that meet confidence/evidence thresholds."""
    from tars.cli.brain_review import BrainReviewEngine

    async def _run() -> None:
        db, store, cl, ver, promo = await _get_components()
        try:
            engine = BrainReviewEngine(db, store)
            approved = await engine.auto_approve_eligible(
                min_confidence=min_confidence,
                min_evidence=min_evidence,
            )
            if approved:
                for n in approved:
                    console.print(
                        f"  [tars.success]Auto-approved PR #{n}[/tars.success]"
                    )
            else:
                console.print("[tars.dim]No PRs eligible for auto-approval.[/tars.dim]")
        finally:
            await db.close()

    asyncio.run(_run())
