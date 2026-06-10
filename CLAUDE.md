# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
pip install -e ".[dev]"                    # install with dev deps
pip install -e ".[dev,embeddings]"         # include sentence-transformers

ruff check src/ tests/                     # lint
ruff format src/ tests/                    # auto-format
pytest tests/unit/ tests/integration/ -v   # run tests
pytest tests/unit/test_config.py -v        # single test file
pytest tests/unit/test_db.py::test_migrations -v  # single test
mypy src/                                  # type check (strict mode)

tars version                               # verify CLI works
tars init                                  # create ~/.tars/ with config + DB
```

## Architecture

TARS is a persistent, self-hosted AI agent with a versioned "visible brain." Product spec is in `TARS-product-documentation.md`; build phases are in `IMPLEMENTATION-PLAN.md`.

### Module Layout (`src/tars/`)

- **core/** — foundation: `config.py` (Pydantic TarsConfig from `~/.tars/config.toml` + env vars), `db.py` (async SQLite with WAL mode + migration runner), `log.py` (Rich-based logging)
- **cli/** — Typer CLI app. Entry point: `tars.cli.app:main`
- **migrations/** — numbered SQL files applied by `db.run_migrations()`. Schema tracked in `_migrations` table with checksums
- **genome/** — the brain: lessons (heuristics), episodes, failure models, confidence math, changelog, versioning. Core IP of the product
- **router/** — model routing across tiers (local/cheap/frontier via litellm), budget tracking, cost receipts
- **agent/** — agent loop (plan→gate→act→verify→record), compiled context assembly, deny-all permission system
- **tools/** — sandboxed tool implementations (shell, filesystem, web_fetch)
- **gateway/** — asyncio daemon, session management, action ledger (hash-chained), kill switch
- **channels/** — message channel adapters (CLI, Telegram)
- **doorman/** — event-driven wake triggers (cron, file watch, IMAP IDLE) with local-model gatekeeper
- **review/** — Sunday Self-Review weekly growth report
- **eval/** — A/B eval harness comparing task success with/without lessons

### Key Design Decisions

- **Compiled context, not transcript replay.** Each model call gets a freshly assembled context (goal + state + relevant lessons + failure warnings). Raw history is never replayed. This prevents context rot and keeps cost near-linear.
- **Bayesian confidence on lessons.** Beta(supporting+1, contradicting+1) with 90-day decay half-life. Origin evidence weighted at 0.3 to prevent circular self-promotion. Promotion requires ≥2 fresh application episodes.
- **Hash-chained action ledger.** Every tool execution appended with SHA-256 chain for tamper evidence.
- **Deny-all permissions.** Every capability must be explicitly granted, scoped, and optionally time-boxed.
- **All I/O is async.** Database via aiosqlite, HTTP via httpx, daemon via asyncio event loop.
- **SQLite single-file storage** at `~/.tars/tars.db`. No external DB server. WAL mode for read concurrency.
- **No FastAPI/SQLAlchemy/Celery.** Daemon uses Unix socket + JSON-RPC. Raw SQL with aiosqlite. asyncio event loop for concurrency.

### Data Flow

User message → Channel → Gateway → Agent Loop → (compiled context from Genome + Lesson Server) → Model Router (picks cheapest capable tier) → Tool execution (sandboxed, permission-gated) → Episode recorded → Learning Loop extracts candidate lessons → Genome updated → Receipt returned to user.

## Config

`~/.tars/config.toml` with sections: `[models]` (3 tiers: local/cheap/frontier), `[budget]` (daily INR limits), `[telegram]`, `[doorman]`. Env override: `TARS_DATA_DIR`, `TARS_TELEGRAM_TOKEN`.

## Conventions

- `from __future__ import annotations` in every module
- Ruff rules: E, F, I, N, W, UP, B, SIM (B008 ignored for typer.Option). Line length 100
- Async tests use `@pytest.mark.asyncio` with `asyncio_mode = "auto"` in pyproject.toml
- IDs are ULIDs (time-ordered, via python-ulid)
- Loggers: `get_logger("module_name")` → prefixed as `tars.module_name`
