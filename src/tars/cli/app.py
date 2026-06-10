from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.panel import Panel

from tars import __version__
from tars.cli.brain import brain_app
from tars.cli.chat import chat
from tars.cli.cost import cost_app
from tars.cli.daemon_cmd import kill, start, status, stop
from tars.cli.eval_cmd import eval_cmd
from tars.cli.review_cmd import review
from tars.cli.theme import console, print_banner
from tars.core.config import DEFAULT_CONFIG_TOML, load_config
from tars.core.db import Database
from tars.core.log import setup_logging

app = typer.Typer(
    name="tars",
    help="TARS -- The first AI agent with a brain you can watch grow.",
    no_args_is_help=True,
)
app.add_typer(brain_app)
app.add_typer(cost_app)
app.command()(chat)
app.command()(start)
app.command()(stop)
app.command(name="status")(status)
app.command()(kill)
app.command()(review)
app.command(name="eval")(eval_cmd)


@app.command()
def doctor(
    security: bool = typer.Option(False, "--security", "-s", help="Include security audit"),
    fix: bool = typer.Option(False, "--fix", "-f", help="Attempt auto-remediation"),
) -> None:
    """Run diagnostic checks on TARS installation."""
    from tars.doctor.checks import DoctorEngine
    from tars.doctor.fixes import DoctorFixer

    async def _run() -> None:
        cfg = load_config()
        engine = DoctorEngine(cfg)
        report = await engine.run_all(include_security=security)

        severity_style = {
            "error": "tars.error",
            "warn": "tars.warn",
            "info": "tars.dim",
        }

        console.print()
        console.print("[tars.accent]TARS Doctor[/tars.accent]")
        console.print()

        for check in report.checks:
            if check.passed:
                icon = "[tars.success]OK[/tars.success]"
            else:
                icon = "[tars.error]FAIL[/tars.error]"
            style = severity_style.get(check.severity, "tars.dim")
            console.print(f"  {icon}  {check.name:.<25s} [{style}]{check.message}[/{style}]")

        console.print()
        console.print(
            f"  [tars.success]{report.passed} passed[/tars.success]"
            f"  [tars.error]{report.failed} failed[/tars.error]"
        )

        if fix and report.failed > 0:
            console.print()
            console.print("[tars.accent]Attempting fixes...[/tars.accent]")
            fixer = DoctorFixer(cfg)
            for check in report.checks:
                if not check.passed and check.fixable:
                    result = await fixer.fix(check)
                    if result:
                        console.print(
                            f"  [tars.success]Fixed:[/tars.success] {check.name} — {result}"
                        )

    asyncio.run(_run())


@app.command()
def curves(
    format: str = typer.Option(
        "terminal", "--format", "-f", help="terminal|svg|badge|json"
    ),
    output: Path = typer.Option(
        ".", "--output", "-o", help="Output directory for SVG"
    ),
    period: str = typer.Option("daily", "--period", "-p", help="Period type: daily|weekly|monthly"),
    limit: int = typer.Option(30, "--limit", "-l", help="Number of snapshots"),
) -> None:
    """Show improvement curves and growth metrics."""
    from tars.curves.renderer import CurveRenderer
    from tars.curves.snapshot import SnapshotCollector

    async def _run() -> None:
        cfg = load_config()
        async with Database(cfg.db_path) as db:
            await db.run_migrations(cfg.migrations_dir)
            collector = SnapshotCollector(db)
            snapshots = await collector.list_snapshots(period, limit=limit)
            renderer = CurveRenderer(snapshots)

            if format == "svg":
                path = renderer.save_svg(output)
                console.print(f"  [tars.success]SVG saved:[/tars.success] {path}")
            elif format == "badge":
                console.print(renderer.to_badge())
            elif format == "json":
                console.print(renderer.to_json())
            else:
                console.print(renderer.to_terminal())

    asyncio.run(_run())


@app.command()
def digest() -> None:
    """Show weekly improvement digest."""
    from tars.curves.digest import ImprovementDigest

    async def _run() -> None:
        cfg = load_config()
        async with Database(cfg.db_path) as db:
            await db.run_migrations(cfg.migrations_dir)
            d = ImprovementDigest(db)
            console.print(await d.weekly_digest())

    asyncio.run(_run())


@app.command(name="import")
def import_cmd(
    source: str = typer.Argument(help="Source: hermes or openclaw"),
    path: str = typer.Option("", "--path", "-p", help="Custom source directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without importing"),
) -> None:
    """Import lessons from another agent (Hermes Agent, OpenClaw)."""
    from tars.genome.store import GenomeStore

    default_paths = {
        "hermes": "~/.hermes",
        "openclaw": "~/.openclaw",
    }

    async def _run() -> None:
        cfg = load_config()
        async with Database(cfg.db_path) as db:
            await db.run_migrations(cfg.migrations_dir)
            store = GenomeStore(db)
            resolved = Path(path or default_paths.get(source, "")).expanduser()

            if source == "hermes":
                from tars.migrate.hermes import HermesImporter
                importer = HermesImporter(db, store)
            elif source == "openclaw":
                from tars.migrate.openclaw import OpenClawImporter
                importer = OpenClawImporter(db, store)
            else:
                console.print(f"[tars.error]Unknown source: {source}[/tars.error]")
                raise typer.Exit(1)

            result = await importer.import_lessons(str(resolved), dry_run=dry_run)

            prefix = "[dim]DRY RUN[/dim] " if dry_run else ""
            console.print()
            console.print(f"  {prefix}[tars.accent]Import from {source}[/tars.accent]")
            console.print(f"  Found: {result.total_found}")
            console.print(f"  Imported: {result.imported}")
            console.print(f"  Duplicates: {result.duplicates}")

            if result.lessons:
                console.print()
                for lesson in result.lessons[:10]:
                    console.print(f"    [tars.brain]+[/tars.brain] {lesson.statement[:80]}")
                if len(result.lessons) > 10:
                    console.print(f"    ... and {len(result.lessons) - 10} more")

    asyncio.run(_run())


@app.command()
def forget(topic: str = typer.Argument(help="Topic or keyword to forget")) -> None:
    """Forget lessons matching a topic."""
    from tars.genome.changelog import ChangelogManager
    from tars.genome.models import HeuristicStatus
    from tars.genome.store import GenomeStore
    from tars.genome.versioning import BrainVersioning

    async def _run() -> None:
        cfg = load_config()
        async with Database(cfg.db_path) as db:
            await db.run_migrations(cfg.migrations_dir)
            store = GenomeStore(db)
            cl = ChangelogManager(db)
            ver = BrainVersioning(store, cl)

            lessons = await store.list_heuristics()
            matches = [
                h
                for h in lessons
                if topic.lower() in h.statement.lower()
                and h.status not in (HeuristicStatus.REVERTED, HeuristicStatus.DEPRECATED)
            ]

            if not matches:
                console.print(f"[tars.dim]No active lessons matching '{topic}'[/tars.dim]")
                return

            for h in matches:
                await ver.revert_lesson(h.id, reason=f"user forget: {topic}")
                console.print(f"  [tars.error]x Forgot:[/tars.error] {h.statement}")

    asyncio.run(_run())


@app.command()
def teach(
    lesson: str = typer.Argument(help="Lesson to teach TARS"),
    domain: str = typer.Option("", "--domain", "-d", help="Domain scope"),
    tags: list[str] = typer.Option([], "--tag", "-t", help="Tags"),
) -> None:
    """Teach TARS a lesson directly."""
    from tars.genome.changelog import ChangelogManager
    from tars.genome.learning_loop import LearningLoop
    from tars.genome.promotion import PromotionEngine
    from tars.genome.store import GenomeStore

    async def _run() -> None:
        cfg = load_config()
        async with Database(cfg.db_path) as db:
            await db.run_migrations(cfg.migrations_dir)
            store = GenomeStore(db)
            cl = ChangelogManager(db)
            promo = PromotionEngine(store, cl)
            loop = LearningLoop(store, cl, promo)

            hid = await loop.on_correction(statement=lesson, domain=domain, tags=tags or None)
            h = await store.get_heuristic(hid)
            console.print(f"  [tars.brain]~ Learned:[/tars.brain] {lesson}")
            if h:
                from tars.cli.theme import confidence_bar

                bar = confidence_bar(h.confidence)
                console.print(f"    {h.id[:12]} | {bar} | {h.status.value}")

    asyncio.run(_run())


mcp_app = typer.Typer(name="mcp", help="Manage MCP server connections.")
app.add_typer(mcp_app)


@mcp_app.command(name="list")
def mcp_list() -> None:
    """List configured MCP servers and their status."""
    cfg = load_config()
    servers = cfg.mcp.servers

    if not servers:
        console.print("  [tars.dim]No MCP servers configured.[/tars.dim]")
        console.print("  [dim]Add servers to ~/.tars/config.toml under [mcp_servers.*][/dim]")
        return

    console.print()
    console.print("[tars.accent]MCP Servers[/tars.accent]")
    console.print()
    for name, entry in servers.items():
        transport = entry.transport
        target = " ".join(entry.command + entry.args) if transport == "stdio" else entry.url
        console.print(f"  [tars.brain]{name}[/tars.brain]  ({transport})  {target}")


@mcp_app.command(name="connect")
def mcp_connect(
    server: str = typer.Argument("", help="Server name (empty = connect all)"),
) -> None:
    """Connect to MCP server(s) and list available tools."""
    from tars.mcp.manager import MCPManager
    from tars.mcp.types import MCPServerConfig, TransportType
    from tars.tools.registry import ToolRegistry

    async def _run() -> None:
        cfg = load_config()
        registry = ToolRegistry()
        manager = MCPManager(registry)

        targets = cfg.mcp.servers
        if server:
            entry = targets.get(server)
            if not entry:
                console.print(f"[tars.error]Unknown server: {server}[/tars.error]")
                raise typer.Exit(1)
            targets = {server: entry}

        configs = [
            MCPServerConfig(
                name=name,
                transport=TransportType(entry.transport),
                command=entry.command,
                args=entry.args,
                env=entry.env,
                url=entry.url,
                headers=entry.headers,
            )
            for name, entry in targets.items()
        ]

        results = await manager.connect_all(configs)

        console.print()
        for name, result in results.items():
            if isinstance(result, int):
                console.print(
                    f"  [tars.success]OK[/tars.success]  {name}  — {result} tools"
                )
                for tool in registry.list_all():
                    if tool.name.startswith(f"mcp.{name}."):
                        short = tool.name.removeprefix(f"mcp.{name}.")
                        console.print(f"       [dim]{short}[/dim]  {tool.description[:60]}")
            else:
                console.print(f"  [tars.error]FAIL[/tars.error]  {name}  — {result}")

        await manager.disconnect_all()

    asyncio.run(_run())


@app.command()
def version() -> None:
    """Print TARS version."""
    print_banner()
    console.print(f"  [tars.accent]v{__version__}[/tars.accent]")


@app.command()
def init(
    data_dir: Path = typer.Option(
        None,
        "--data-dir",
        "-d",
        help="Data directory (default: ~/.tars)",
    ),
) -> None:
    """Initialize TARS: create data directory, config, and database."""
    setup_logging()
    cfg = load_config(data_dir)
    data = cfg.data_dir

    print_banner()

    if data.exists() and cfg.config_path.exists() and cfg.db_path.exists():
        console.print(f"  [tars.warn]Already initialized at {data}[/tars.warn]")
        raise typer.Exit(0)

    data.mkdir(parents=True, exist_ok=True)

    if not cfg.config_path.exists():
        cfg.config_path.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")

    async def _init_db() -> int:
        async with Database(cfg.db_path) as db:
            return await db.run_migrations(cfg.migrations_dir)

    applied = asyncio.run(_init_db())

    console.print(
        Panel(
            f"[tars.success]Brain initialized.[/tars.success]\n\n"
            f"  [dim]Data:[/dim]    {data}\n"
            f"  [dim]Config:[/dim]  {cfg.config_path}\n"
            f"  [dim]DB:[/dim]      {cfg.db_path} ({applied} migrations)\n\n"
            "[bold]Next steps:[/bold]\n"
            "  1. Configure models  ->  [cyan]~/.tars/config.toml[/cyan]\n"
            "  2. Set API keys      ->  [cyan]export OPENAI_API_KEY=...[/cyan]\n"
            "  3. Start chatting    ->  [cyan]tars chat[/cyan]\n"
            '  4. Teach something   ->  [cyan]tars teach "always lint before commit"[/cyan]',
            title="[tars.accent]* TARS Ready[/tars.accent]",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def main() -> None:
    app()
