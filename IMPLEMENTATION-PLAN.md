# TARS v0.1 MVP — Implementation Plan

## Context

TARS is a persistent, self-hosted AI agent with a "visible brain" — every lesson it learns is versioned, evidence-backed, and reversible. The repo is empty (just README + product doc). We need to build the full MVP defined in the product doc §7: gateway daemon, agent loop, compiled context, model router, genome (the brain), doorman, action ledger, kill switch, Sunday review, and eval harness.

This plan covers all 9 phases in dependency order. Each phase produces a working, testable artifact.

---

## Phase 1: Foundation

**Goal:** Installable project with config, DB, CLI skeleton, CI.

**Files to create:**
- `pyproject.toml` — hatchling build, all deps declared, `tars` entry point
- `src/tars/__init__.py` — version string
- `src/tars/__main__.py` — `python -m tars` support
- `src/tars/core/config.py` — load `~/.tars/config.toml` + env vars (pydantic model)
- `src/tars/core/db.py` — async SQLite connection manager, schema migration runner (WAL mode)
- `src/tars/core/logging.py` — structured logging via `rich.logging.RichHandler`
- `src/tars/cli/app.py` — Typer app: `tars version`, `tars init` (creates `~/.tars/`, config, empty DB)
- `tests/conftest.py` — fixtures: temp DB, temp config dir
- `tests/unit/test_config.py`
- `.github/workflows/ci.yml` — ruff + pytest

**Key dependencies:**
- `typer[all]`, `rich`, `pydantic>=2.0`, `aiosqlite`, `litellm`, `httpx`
- `python-telegram-bot>=21`, `watchdog`, `croniter`, `imapclient`
- `python-ulid` (time-ordered IDs)
- Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`

**Config file** (`~/.tars/config.toml`): model providers, budget limits, telegram token, doorman triggers.

**DB location:** `~/.tars/tars.db`

**Deliverable:** `pip install -e .` works, `tars version` prints version, `tars init` creates data dir + config + empty DB.

---

## Phase 2: Genome Core

**Goal:** The brain works in isolation — create/query/update/version/revert lessons, `tars brain` CLI.

**Files to create:**
- `src/tars/genome/models.py` — Pydantic models: Episode, Heuristic, Evidence, FailureModel
- `src/tars/genome/store.py` — SQLite CRUD for all genome tables (episodes, heuristics, evidence, failure_models, changelog)
- `src/tars/genome/confidence.py` — Beta(α,β) math: `compute_confidence()`, `apply_decay()`, weighted evidence
- `src/tars/genome/changelog.py` — append-only hash-chained log, diff between timestamps, revert by ID/date
- `src/tars/genome/versioning.py` — `brain_diff()`, `brain_log()`, `revert_lesson()`, `revert_to_date()`
- `src/tars/genome/promotion.py` — check promotion criteria (≥3 evidence, ≥0.70 conf, ≥2 fresh apps), execute transitions
- `src/tars/genome/lesson_server.py` — scope-based SQL filter + embedding similarity ranking + top-k retrieval
- `src/tars/genome/failure_models.py` — CRUD + signature-match lookup
- `src/tars/genome/embeddings.py` — lightweight embedding service (sentence-transformers MiniLM or fallback to keyword matching)
- `src/tars/genome/conflict.py` — pairwise scope-overlap + semantic similarity, LLM confirmation
- `src/tars/cli/brain.py` — `tars brain` (rich table), `tars brain log`, `tars brain diff --since`, `tars brain revert`, `tars forget`
- `tests/unit/test_confidence.py`, `test_heuristic.py`, `test_episode.py`
- `tests/integration/test_genome_lifecycle.py`

**DB schema (6 tables):**
- `episode` — goal, context_features (JSON), action_trace (JSON), outcome, cost_breakdown (JSON), lessons_applied
- `heuristic` — statement, scope (JSON), status (CANDIDATE/ACTIVE/DEPRECATED/REVERTED), confidence, alpha, beta, evidence count, origin_type (EXTRACTED/TAUGHT/IMPORTED)
- `evidence` — junction table: heuristic_id, episode_id, direction (SUPPORTING/CONTRADICTING), weight (1.0 normal, 0.3 origin, 0.0 reverted)
- `failure_model` — signature, root_cause, recovery_path, scope
- `changelog` — hash-chained: entity_type, entity_id, operation, field_changes (JSON), snapshot (JSON)
- `permissions` — capability, scope, granted_at, expires_at, revoked_at

**Confidence math:**
- `confidence = alpha / (alpha + beta)` where `alpha = weighted_supporting + 1`, `beta = weighted_contradicting + 1`
- Decay: `effective_evidence *= 0.5^(days_since_last_evidence / 90)` — 90-day half-life
- Auto-deprecate ACTIVE lessons when decayed confidence < 0.45

**Promotion gates:** ≥3 weighted evidence AND ≥0.70 confidence AND ≥2 fresh (non-origin) supporting episodes. Prevents circular self-promotion.

**Deliverable:** `tars brain` shows lessons in a rich table. Insert/promote/revert lessons. History and diff work. All genome math tested.

---

## Phase 3: Model Router + Receipts

**Goal:** Call any configured model, route by tier, produce cost receipts.

**Files to create:**
- `src/tars/router/providers.py` — adapters wrapping litellm: `OllamaProvider`, `APIProvider`, standard `ModelResponse` with token counts
- `src/tars/router/model_router.py` — `route(task_class, stakes) -> provider+model`; tiers: local→cheap→frontier
- `src/tars/router/budget.py` — daily/task spend tracking, `BudgetExceeded` exception
- `src/tars/router/receipt.py` — `Receipt` pydantic model, rich formatting
- `src/tars/cli/cost.py` — `tars cost`, `tars cost --month`
- `tests/unit/test_model_router.py`, `test_receipt.py`

**Deliverable:** `await router.complete(messages, task_class, stakes)` picks model, calls it, returns response + receipt.

---

## Phase 4: Agent Loop + Tools + Permissions

**Goal:** User gives task → agent plans → requests permissions → executes tools → verifies → records episode.

**Files to create:**
- `src/tars/agent/context_compiler.py` — assemble compiled context: goal + task state + scope-matched lessons + failure warnings + working data. No transcript replay.
- `src/tars/agent/permissions.py` — deny-all default, grant/revoke, scope checking, time-boxed grants
- `src/tars/agent/planner.py` — decompose goal into steps via model call
- `src/tars/agent/loop.py` — plan → gate (permission) → act (tool) → verify → record (episode)
- `src/tars/tools/base.py` — `Tool` ABC: name, description, parameters_schema, execute()
- `src/tars/tools/shell.py` — shell execution with timeout + path restrictions
- `src/tars/tools/filesystem.py` — read/write/list with path scoping
- `src/tars/tools/web_fetch.py` — HTTP GET/POST with domain allowlist
- `src/tars/sandbox/executor.py` — subprocess wrapper, timeout, output capture
- `src/tars/gateway/action_ledger.py` — hash-chained append-only log: who/what/when/why
- `tests/unit/test_permissions.py`, `test_action_ledger.py`, `test_context_compiler.py`
- `tests/integration/test_agent_loop.py`

**Deliverable:** Give agent "list files in /tmp" → plans shell command → requests permission → executes → returns result → episode recorded → action ledger entry created.

---

## Phase 5: Gateway Daemon + CLI Channel

**Goal:** `tars start` launches persistent daemon, `tars chat` connects interactively.

**Files to create:**
- `src/tars/gateway/daemon.py` — asyncio main loop, PID file, signal handlers (SIGTERM graceful, SIGINT immediate)
- `src/tars/gateway/server.py` — Unix domain socket (loopback TCP fallback on WSL2), JSON-RPC: submit_task, get_status, kill, get_brain
- `src/tars/gateway/session.py` — session lifecycle, active task tracking, timeout
- `src/tars/gateway/kill_switch.py` — halt loop, revoke permissions, log
- `src/tars/channels/base.py` — `Channel` ABC
- `src/tars/channels/cli_channel.py` — stdin/stdout, connects to daemon socket
- `src/tars/core/events.py` — event types, asyncio Queue-based internal bus
- `src/tars/cli/chat.py` — `tars chat` interactive REPL with rich formatting
- `src/tars/cli/daemon.py` — `tars start`, `tars stop`, `tars status`, `tars kill`
- `tests/integration/test_gateway.py`

**Deliverable:** `tars start` runs daemon. `tars chat` opens session. User types task, agent executes, prints receipt. `tars kill` stops everything.

---

## Phase 6: Teach-and-it-Sticks + Learning Loop

**Goal:** User corrections become candidate lessons. Brain grows from real usage.

**Files to create/modify:**
- `src/tars/genome/learning_loop.py` — on TaskCompleted: call cheap model to extract candidate lessons from episode; on CorrectionReceived: create taught lesson directly
- Extend `agent/loop.py` — detect corrections ("actually do X", "no, always Y"), emit CorrectionReceived event
- Extend `genome/promotion.py` — after each episode, re-evaluate CANDIDATE lessons
- Extend `genome/lesson_server.py` — on teach, acknowledge with scope + confidence
- Extend `cli/brain.py` — `tars forget "<topic>"` deprecates matching lessons
- `src/tars/genome/prompts/` — LLM prompt templates for episode analysis, correction→lesson extraction
- `tests/integration/test_teach_and_stick.py`

**Deliverable:** Do a task → teach a correction → see it in `tars brain` → watch confidence grow over more tasks. The "Minute-5 brain moment" works end-to-end.

---

## Phase 7: Telegram Channel

**Files to create:**
- `src/tars/channels/telegram.py` — python-telegram-bot async handler, maps messages to events, inline permission buttons
- Extend `cli/app.py` — `tars telegram setup` guided config

**Deliverable:** Chat with TARS on Telegram. Same brain, receipts, permissions.

---

## Phase 8: Doorman

**Files to create:**
- `src/tars/doorman/manager.py` — trigger registration + dispatch
- `src/tars/doorman/triggers/cron.py` — croniter scheduling, asyncio sleep-until
- `src/tars/doorman/triggers/file_watch.py` — watchdog observer
- `src/tars/doorman/triggers/imap.py` — IMAP IDLE listener
- `src/tars/doorman/gatekeeper.py` — local/cheap model decides "worth waking frontier?"
- `tests/integration/test_doorman.py`

**Deliverable:** Configure cron trigger → TARS wakes, does task, goes idle. Idle cost: zero model calls.

---

## Phase 9: Sunday Review + Eval Harness

**Files to create:**
- `src/tars/review/sunday_review.py` — query week's episodes, compute stats, format report, send via channels
- `src/tars/eval/harness.py` — run task suite with/without lessons, compare success rates, McNemar's test for significance
- `src/tars/cli/eval_cmd.py` — `tars eval --suite path/to/suite.json`
- `tests/unit/test_sunday_review.py`
- `tests/integration/test_eval_harness.py`

**Deliverable:** `tars eval` prints lift with p-value. Sunday review lands in CLI + Telegram.

---

## Verification

After each phase:
1. All existing tests pass (`pytest tests/unit/ tests/integration/`)
2. `ruff check` and `ruff format --check` pass
3. Phase-specific smoke test works manually
4. End-to-end after Phase 6: the "first five minutes" flow from product doc §4.2

Final MVP acceptance:
- New user reaches Minute-5 brain moment in <5 minutes
- Idle cost <₹1/day
- `tars eval` on 200-task suite shows statistically meaningful lift
- Zero critical security findings in defaults

---

## Project Structure (final)

```
TARS/
├── pyproject.toml
├── LICENSE (MIT)
├── README.md
├── .github/workflows/ci.yml
├── src/tars/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli/          (app, chat, brain, cost, eval_cmd, daemon)
│   ├── core/         (config, db, events, logging)
│   ├── gateway/      (daemon, server, session, kill_switch, action_ledger)
│   ├── channels/     (base, cli_channel, telegram)
│   ├── agent/        (loop, planner, context_compiler, permissions)
│   ├── tools/        (base, shell, filesystem, web_fetch)
│   ├── router/       (model_router, providers, budget, receipt)
│   ├── genome/       (models, store, confidence, changelog, versioning,
│   │                  learning_loop, lesson_server, promotion, conflict,
│   │                  failure_models, embeddings, prompts/)
│   ├── doorman/      (manager, triggers/, gatekeeper)
│   ├── sandbox/      (executor)
│   ├── review/       (sunday_review)
│   └── eval/         (harness)
└── tests/
    ├── conftest.py
    ├── unit/
    ├── integration/
    └── e2e/
```
