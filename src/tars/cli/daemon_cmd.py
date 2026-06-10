from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys

import typer

from tars.cli.theme import console
from tars.core.config import load_config
from tars.gateway.daemon import Daemon


def start(
    foreground: bool = typer.Option(False, "--foreground", "-f", help="Run in foreground"),
) -> None:
    """Start the TARS daemon."""
    cfg = load_config()

    if not cfg.db_path.exists():
        console.print("[tars.error]Not initialized. Run 'tars init' first.[/tars.error]")
        raise typer.Exit(1)

    existing_pid = Daemon.read_pid(cfg)
    if existing_pid:
        console.print(f"[tars.warn]Already running (pid {existing_pid})[/tars.warn]")
        raise typer.Exit(1)

    if foreground:
        console.print("[tars.accent]* Starting TARS (Ctrl+C to stop)...[/tars.accent]")
        daemon = Daemon(cfg)
        asyncio.run(daemon.run_forever())
    else:
        proc = subprocess.Popen(
            [sys.executable, "-m", "tars.gateway.daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        console.print(
            f"[tars.success]* TARS daemon started[/tars.success] [dim](pid {proc.pid})[/dim]"
        )


def stop() -> None:
    """Stop the TARS daemon."""
    cfg = load_config()
    pid = Daemon.read_pid(cfg)

    if not pid:
        console.print("[tars.dim]TARS is not running.[/tars.dim]")
        raise typer.Exit(0)

    try:
        os.kill(pid, signal.SIGTERM)
        console.print(f"[tars.success]* Stopped[/tars.success] [dim](pid {pid})[/dim]")
    except ProcessLookupError:
        console.print("[tars.dim]Process already gone.[/tars.dim]")
        pid_path = cfg.data_dir / "tars.pid"
        pid_path.unlink(missing_ok=True)


def status() -> None:
    """Check TARS daemon status."""
    cfg = load_config()
    pid = Daemon.read_pid(cfg)

    if pid:
        console.print(f"[tars.active]* Running[/tars.active] [dim](pid {pid})[/dim]")
    else:
        console.print("[dim]o Not running[/dim]")


def kill() -> None:
    """Emergency kill: stop daemon, revoke all permissions."""
    cfg = load_config()
    pid = Daemon.read_pid(cfg)

    if pid:
        try:
            if sys.platform == "win32":
                os.kill(pid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGKILL)
            console.print(f"[tars.error]x Killed daemon[/tars.error] [dim](pid {pid})[/dim]")
        except ProcessLookupError:
            pass

    from tars.agent.permissions import PermissionManager
    from tars.core.db import Database

    async def _revoke() -> None:
        async with Database(cfg.db_path) as db:
            await db.run_migrations(cfg.migrations_dir)
            pm = PermissionManager(db)
            count = await pm.revoke_all()
            if count:
                console.print(f"[tars.error]x Revoked {count} permission(s)[/tars.error]")

    asyncio.run(_revoke())

    pid_path = cfg.data_dir / "tars.pid"
    pid_path.unlink(missing_ok=True)
    console.print("\n[bold red]  X KILL SWITCH ACTIVATED[/bold red]\n")
