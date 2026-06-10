from __future__ import annotations

import asyncio

import typer
from rich.panel import Panel

from tars.agent.loop import StepStatus
from tars.cli.theme import OUTCOME_ICON, STEP_ICON, budget_bar, console
from tars.core.config import load_config
from tars.core.db import Database
from tars.gateway.server import GatewayServer
from tars.gateway.session import SessionStatus
from tars.genome.changelog import ChangelogManager
from tars.genome.learning_loop import LearningLoop, detect_correction
from tars.genome.promotion import PromotionEngine


def chat() -> None:
    """Start an interactive chat session with TARS."""
    asyncio.run(_chat_loop())


async def _prompt(text: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: console.input(text))


async def _ask_permission(capability: str) -> bool:
    answer = await _prompt(
        f"  [tars.warn]TARS needs [bold]{capability}[/bold] permission. Grant? [y/N]:[/tars.warn] "
    )
    return answer.strip().lower() in ("y", "yes")


async def _chat_loop() -> None:
    cfg = load_config()

    if not cfg.db_path.exists():
        console.print("[tars.error]Not initialized. Run 'tars init' first.[/tars.error]")
        raise typer.Exit(1)

    db = Database(cfg.db_path)
    await db.connect()
    await db.run_migrations(cfg.migrations_dir)

    server = GatewayServer(cfg, db)
    session = server.session_manager.create(channel="cli")

    cl = ChangelogManager(db)
    promo = PromotionEngine(server.genome_store, cl)
    learner = LearningLoop(server.genome_store, cl, promo)

    lessons = await server.genome_store.list_heuristics()
    active_count = sum(1 for h in lessons if h.status.value == "ACTIVE")

    console.print()
    console.print(
        Panel(
            f"[bold]Session[/bold] [dim]{session.id[:12]}[/dim]    "
            f"[tars.brain]~ {active_count} lessons loaded[/tars.brain]\n\n"
            "[dim]Type a task, teach a lesson, or use commands:[/dim]\n"
            "  [cyan]/teach[/cyan] <lesson>  teach TARS something\n"
            "  [cyan]/status[/cyan]          budget & session\n"
            "  [cyan]/quit[/cyan]            exit",
            title="[tars.accent]* TARS[/tars.accent]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()

    try:
        while session.status != SessionStatus.KILLED:
            try:
                line = await _prompt("[bold cyan]you >[/bold cyan] ")
            except (EOFError, KeyboardInterrupt):
                break

            line = line.strip()
            if not line:
                continue

            if line.lower() in ("/quit", "/exit", "/q"):
                console.print("  [dim]Session ended.[/dim]")
                break

            if line.startswith("/grant "):
                cap = line[7:].strip()
                await server.permissions.grant(cap)
                console.print(f"  [tars.success]+ Granted:[/tars.success] {cap}")
                continue

            if line == "/perms":
                perms = await server.permissions.list_active()
                if not perms:
                    console.print("  [dim]No active permissions[/dim]")
                else:
                    for p in perms:
                        console.print(
                            f"  [tars.active]*[/tars.active] {p.capability} [dim]({p.scope})[/dim]"
                        )
                continue

            if line == "/status":
                budget = await server.router.get_budget_status()
                spent = budget.get("spent_inr", 0)
                limit = budget.get("limit_inr", 50)
                bar = budget_bar(spent, limit)
                console.print(
                    f"  [bold]Session[/bold] {session.id[:12]}  "
                    f"Tasks: {session.task_count}  "
                    f"Cost: Rs{session.total_cost_inr:.4f}"
                )
                console.print(f"  [bold]Budget[/bold]  {bar}")
                continue

            if line.startswith("/teach "):
                lesson_text = line[7:].strip()
                if lesson_text:
                    hid = await learner.on_correction(statement=lesson_text)
                    console.print(
                        f"  [tars.brain]~ Learned:[/tars.brain] {lesson_text}\n"
                        f"    [dim]{hid[:12]}[/dim]"
                    )
                else:
                    console.print("  [tars.warn]Usage: /teach <lesson>[/tars.warn]")
                continue

            if line.startswith("/"):
                console.print(f"  [tars.warn]Unknown command: {line}[/tars.warn]")
                continue

            correction = detect_correction(line)
            if correction:
                hid = await learner.on_correction(statement=correction)
                console.print(
                    f"  [tars.brain]~ Learned from correction:[/tars.brain] "
                    f"{correction}\n"
                    f"    [dim]{hid[:12]}[/dim]"
                )
                continue

            await _run_task(server, session, learner, line)

    finally:
        server.session_manager.remove(session.id)
        await db.close()


async def _run_task(
    server: GatewayServer,
    session: object,
    learner: LearningLoop,
    goal: str,
) -> None:
    with console.status("[tars.accent]Thinking...[/tars.accent]", spinner="dots"):
        result = await server.submit_task(session, goal=goal)

    denied_caps: list[str] = []
    for sr in result.step_results:
        if sr.status == StepStatus.PERMISSION_DENIED and sr.step.requires_permission:
            denied_caps.append(sr.step.requires_permission)

    if denied_caps:
        granted_any = False
        for cap in dict.fromkeys(denied_caps):
            if await _ask_permission(cap):
                await server.permissions.grant(cap)
                console.print(f"  [tars.success]+ Granted:[/tars.success] {cap}")
                granted_any = True
            else:
                console.print(f"  [dim]Skipped {cap}[/dim]")

        if granted_any:
            console.print()
            with console.status("[tars.accent]Retrying...[/tars.accent]", spinner="dots"):
                result = await server.submit_task(session, goal=goal)

    console.print()
    for sr in result.step_results:
        icon = STEP_ICON.get(sr.status.value, ".")
        console.print(f"  {icon} [bold]{sr.step.tool}[/bold] [dim]{sr.step.description}[/dim]")
        if sr.tool_result and sr.tool_result.output:
            output = sr.tool_result.output[:500]
            for output_line in output.split("\n")[:5]:
                console.print(f"    [dim]{output_line}[/dim]")
        if sr.error:
            console.print(f"    [tars.error]{sr.error}[/tars.error]")

    outcome_icon = OUTCOME_ICON.get(result.outcome.value, ".")
    console.print(
        f"\n  {outcome_icon} [bold]{result.outcome.value}[/bold]"
        f" [dim]| Rs{result.total_cost_inr:.4f}[/dim]"
    )

    if result.episode_id:
        ep = await server.genome_store.get_episode(result.episode_id)
        if ep:
            new_ids = await learner.on_episode_completed(ep)
            if new_ids:
                console.print(
                    f"  [tars.brain]~ Extracted {len(new_ids)} candidate lesson(s)[/tars.brain]"
                )
    console.print()
