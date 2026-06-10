# TARS — Product Documentation

**The first AI agent with a brain you can watch grow.**

> Version: 0.1 (pre-launch draft) · Last updated: June 2026 · Status: Design-complete, build-in-progress

---

## 1. Product Overview

### 1.1 What TARS is

TARS is a persistent, self-hosted AI agent for Linux that lives on your machine, works through your terminal and messaging apps, and — unlike every other agent in the market — **learns in the open**.

Every lesson TARS learns from working with you is recorded like a pull request to its own mind: a plain-language statement, the evidence behind it, a confidence score, and a scope describing exactly when it applies. You can read your agent's brain, approve or reject what it learns, diff who it was last month against who it is today, and revert a bad lesson with one command — like git, but for an agent's judgment.

It is also the first agent designed around a budget. Every task ends with a receipt. Every model call is routed to the cheapest model that can do the job. The agent never wakes a frontier model to ask "is it daytime yet?"

### 1.2 What TARS is not

- Not a chatbot. TARS executes: shell, files, browser, email, schedules.
- Not a cloud service. Self-hosted, MIT-style open source, bring-your-own-API-key or local models.
- Not another memory layer. Memory stores what happened. TARS extracts and *validates* what should change about future behavior.
- Not a black box. Nothing about TARS's behavior changes without a visible, reversible record.

### 1.3 One-line pitches

| Audience | Pitch |
|---|---|
| Hacker News / GitHub | "My agent sends me a weekly report of what it learned, with evidence — and I can revert its brain like git." |
| Developers | "Teach it once. Watch it stick. See the receipts." |
| Teams / enterprise | "The only self-improving agent with an audit trail, a kill switch, and a budget." |
| General | "Your agent, with receipts." |

---

## 2. The Problem (validated, June 2026)

The 2025–26 agent boom (OpenClaw: 100k+ GitHub stars and millions of users; Hermes Agent: 100k+ stars in seven weeks) proved enormous demand for persistent personal agents — and then proved exactly how the current architecture fails. Five pain points, each documented in public reports:

### P1 — Security catastrophe
- 135,000+ internet-exposed OpenClaw instances found by scanners; 12,800+ directly exploitable via RCE, leaking API keys, chat logs, credentials (SecurityScorecard / Immersive Labs, 2026).
- ~900 malicious or dangerously flawed skills found on ClawHub; skills run with the agent's full permissions (Koi Security, Snyk).
- Hermes Agent's independent audit: default posture is ALLOW-ALL; agent-created skill files act as persistent prompt-injection vectors with only regex guards.
- No enterprise kill switch exists for either: security teams cannot inventory or disable deployed instances.
- China's CNCERT issued two national warnings about agent deployments in 2026.

### P2 — Runaway cost
- Documented user bills: $3,600/month; $200 burned in one day by a loop; $50/day from a 5-minute email-check heartbeat; $18.75 overnight asking, effectively, "is it daytime yet?" at 120k tokens per check.
- Root cause is architectural: naive loops re-send the entire history every turn, producing quadratic cost growth.

### P3 — Reliability collapse on long horizons
- Reliability is the #1 concern of agent buyers (CB Insights): ~80% accuracy on simple tasks falls to ~50% on complex ones.
- "Context rot" is now a named phenomenon: agents degrade, repeat themselves, and forget constraints as context accumulates. One operator burned 135M tokens in 24 hours while the agent "forgot its own configuration and spent the night talking to itself."
- Research shows >50% capability degradation well before 100k tokens, with safety behavior shifting unpredictably.

### P4 — Unobservable learning
- Self-learning agents (Hermes) encode lessons as freeform Markdown with no versioning, no audit log, no promotion gate, no rollback. A wrong lesson causes silent behavioral drift discovered weeks later — "no PR, no diff, no alert."
- Community verdict: an unmonitored self-learning agent is "a junior dev with zero audit trail."

### P5 — Unsafe setup by default
- Safe deployment requires terminal expertise and careful data partitioning; a literal cottage industry of paid installers ($15–$100, in-home service at the high end) emerged. Users buy secondhand machines just to contain the blast radius.

**The pattern:** every pain point is a symptom of one design — *think → act, forever, with full trust, full context, full price, and invisible learning*. TARS is a different loop, not another feature on the old one.

---

## 3. Product Identity & Differentiation

### 3.1 The hero capability: the Visible Brain

Nobody — not Hermes, not OpenClaw, not the memory-layer ecosystem — can show you their agent's mind. TARS makes the agent's evolving judgment a first-class, inspectable, reversible artifact.

- Every lesson is a structured object: statement, scope, confidence, evidence trail.
- Lessons arrive as **proposals** ("brain PRs") you can approve, edit, reject, or let auto-promote on evidence.
- The brain has a **history**: diff this week vs last month; see exactly which task taught it what.
- **Revert Tuesday**: one command undoes a bad lesson and everything downstream of it.

This is simultaneously the magic moment (inherently screenshot-able), the trust answer to P4, and structurally hard for incumbents to copy (their skills are prose; ours are evidence-backed records).

### 3.2 Differentiation matrix

| Capability | OpenClaw | Hermes Agent | **TARS** |
|---|---|---|---|
| Persistent personal agent | ✅ | ✅ | ✅ |
| Self-improvement | ❌ (manual skills) | ✅ (invisible) | ✅ **visible, evidence-backed, reversible** |
| Learning audit trail / rollback | ❌ | ❌ | ✅ |
| Confidence + scope per lesson | ❌ | ❌ | ✅ |
| Cost receipts per task | ❌ | ❌ | ✅ |
| Budget-constrained planning | ❌ | ❌ | ✅ |
| Idle cost ≈ ₹0 (event-driven wake) | ❌ (heartbeat polling) | partial | ✅ |
| Deny-all permissions by default | ❌ (allow-heavy) | ❌ (ALLOW-ALL default) | ✅ |
| Kill switch + action ledger | ❌ | ❌ | ✅ |
| Proven lift (A/B eval harness) | ❌ | ❌ | ✅ |

---

## 4. User Experience

### 4.1 Personas

1. **The Power Developer ("Asha")** — runs agents on a VPS, burned by an OpenClaw bill, wants automation she can trust unattended overnight.
2. **The Builder ("Dev")** — building products with agents; needs an agent whose improvement he can demonstrate to users/investors with numbers.
3. **The Cautious Team Lead ("Meera")** — wants agent leverage for her team but cannot deploy anything without audit, permissions, and an off switch.

### 4.2 The first five minutes (critical path)

```
$ curl -fsSL https://tars.dev/install | sh
$ tars init        # picks model provider, sets DENY-ALL permissions, creates brain
$ tars chat
```

1. **Minute 1 — Install.** One command. Secure defaults are not optional flags; deny-all is the starting state. The installer never asks the user to make a security decision they don't understand.
2. **Minute 2 — First task.** User asks for something real ("organize my downloads folder by type"). TARS requests the one permission it needs (`fs:read+write on ~/Downloads`), does the task.
3. **Minute 3 — The receipt.** `Done. 142 files sorted. Cost: ₹2.10 (Haiku 88%, Sonnet 12%). 14s.`
4. **Minute 4 — The teach moment.** User says "actually, keep PDFs in a separate Documents/papers folder." TARS: `Learned (candidate): "PDFs route to ~/Documents/papers" — scope: file-organization tasks. I'll confirm it after a few more tasks. Say 'forget that' anytime.`
5. **Minute 5 — The brain.** `tars brain` opens the dashboard: 1 candidate lesson, its evidence (this conversation), its scope. The user sees their agent's mind for the first time. **This is the moment they screenshot.**

### 4.3 The Sunday Self-Review

Weekly message (chat + dashboard):

```
📊 Week 23 review
Tasks: 34 completed · 91% success (↑ from 84%)
Learned: 2 lessons promoted, 1 candidate rejected (evidence contradicted it)
Reverted: 0
Money: ₹412 spent · ~₹605 saved by routing (59% of calls served by cheap tier)
Top lesson this week: "Reproduce bugs locally before proposing fixes" (conf 0.91, n=14)
```

A growth chart for your agent. No competing product has this.

### 4.4 Everyday interactions

- **Teach-and-it-sticks:** any correction becomes a candidate lesson, acknowledged explicitly with scope. The single most common community complaint — "I already told you this" — becomes structurally impossible to repeat silently.
- **Receipts everywhere:** every task ends with cost, model mix, and duration. `tars cost --month` shows trends.
- **Failure memory:** before risky actions, TARS checks its failure models: "I've failed at this before (missing DB migration, 2 weeks ago). Applying the recovery path first."
- **Brain commands:** `tars brain` (dashboard) · `tars brain diff --since 30d` · `tars brain log` · `tars brain revert <lesson-id|date>` · `tars forget "<topic>"`

---

## 5. Architecture

### 5.1 System diagram

```
            ┌────────────────────────────────────────────────────┐
            │                     CHANNELS                       │
            │     CLI · Telegram · (later: WhatsApp, Slack)      │
            └───────────────┬────────────────────────────────────┘
                            │  normalized events
            ┌───────────────▼────────────────────────────────────┐
            │                 GATEWAY (daemon)                   │
            │  sessions · routing · kill switch · action ledger  │
            └───────┬───────────────────────────────┬────────────┘
                    │                               │
        ┌───────────▼───────────┐       ┌───────────▼───────────┐
        │       DOORMAN         │       │      AGENT LOOP       │
        │ event triggers, tiny  │ wake  │ plan → (gate) → act → │
        │ local model decides   ├──────►│ verify → record       │
        │ if frontier wake is   │       │ compiled context/turn │
        │ worth the cost        │       └───┬─────────┬─────────┘
        └───────────────────────┘           │         │
                                   ┌────────▼───┐ ┌───▼────────────┐
                                   │ EXECUTION  │ │  MODEL ROUTER  │
                                   │ sandbox:   │ │ budget-aware   │
                                   │ shell/fs/  │ │ tier routing:  │
                                   │ browser/   │ │ local→cheap→   │
                                   │ email/cron │ │ frontier       │
                                   └────────┬───┘ └────────────────┘
                                            │ episodes
            ┌───────────────────────────────▼────────────────────┐
            │               TARS GENOME (the brain)              │
            │  Episode Store → Learning Loop → Lesson Server     │
            │  evidence · confidence · scope · promotion gates   │
            │  versioned history · diff · revert · A/B harness   │
            └────────────────────────────────────────────────────┘
```

### 5.2 The Doorman (answers P2)

Heartbeat polling is replaced by **event-driven wake**:
- Code-level triggers where possible: IMAP IDLE for email, webhooks, file watchers (inotify), cron for true schedules.
- When judgment is needed ("is this email worth waking the big model?"), a tiny local model (or cheapest API tier) decides in <1k tokens.
- Frontier models are invoked only for tasks that need them. **Idle cost target: < ₹1/day.**

### 5.3 Compiled Context (answers P2 + P3)

Turns are stateless with respect to raw history. Each model call receives a **freshly compiled context**: current goal, task state, relevant lessons (scope-matched, top-k), relevant failure models, and only the working files/outputs the step needs. Raw transcripts live on disk, summarized into structured state; they are never replayed wholesale. This converts quadratic cost into near-linear and prevents context rot by construction.

### 5.4 Capability Manifests + Ledger (answers P1)

- **Deny-all default.** Every capability (a directory, a domain, a shell command class, an account) must be granted explicitly, and grants are scoped + time-boxed where sensible.
- **Skill manifests.** Every skill declares the exact capabilities it uses; installation shows the manifest; undeclared access is blocked at runtime, not flagged.
- **Action ledger.** Every tool execution is appended to a tamper-evident local log (hash-chained): who/what/when/why (the plan step), with replay.
- **Kill switch.** `tars kill` halts the loop and revokes session credentials instantly; remote kill via signed message for fleet/team deployments.
- **Gateway hardening.** Loopback-only by default, token auth mandatory, no web-exposed dashboard without explicit, loudly-warned opt-in.

### 5.5 The Genome (answers P4 — the core IP)

Three primitives:

**Episode** — every completed task: goal, context features, action trace, outcome, cost, and which lessons were applied.

**Heuristic (lesson)** — `statement · scope · supporting/contradicting evidence · confidence · status`.
- Confidence = mean of Beta(supporting+1, contradicting+1): 0.93 from 62 observations is distinguishable from 0.93 from 3.
- Lifecycle: `CANDIDATE → (evidence ≥ N ∧ conf ≥ 0.7) → ACTIVE → (conf < 0.45 ∨ decay) → DEPRECATED`.
- **Contrast-based promotion:** episodes that generated a hypothesis count at reduced weight; promotion requires fresh episodes where the lesson was actually applied (no circular evidence).
- **Decay:** confidence shrinks toward the uninformed prior without recent confirmation. Lessons rot; TARS knows it.
- **Conflict detection:** contradictory active lessons in overlapping scopes are flagged for the user and logged as under-scoping signals.

**FailureModel** — a recognized failure signature with root cause and recovery path, checked before acting ("have we failed here before?").

All genome mutations are **versioned**: append-only history, diffable, revertible. The brain is a repository.

**Built-in eval harness:** `tars eval` runs the same task suite with and without lesson injection and reports the lift. This is both the engineering guardrail and the marketing engine — TARS is the only agent that can *prove* it is improving.

### 5.6 Model Router (answers P2)

- Tiers: local (Ollama-class) → cheap API → mid → frontier; per-step routing by task class and stakes.
- Per-task and per-day budgets are planning constraints, not after-the-fact alerts: the planner selects approaches that fit the budget or asks before exceeding it.
- Prompt caching exploited by keeping the compiled-context prefix stable.

---

## 6. Security Model (summary)

| Threat (observed in the wild) | TARS control |
|---|---|
| Exposed gateway / RCE | Loopback-only default, mandatory token auth, no unauthenticated web UI |
| Malicious skills (supply chain) | Signed skills, capability manifests, undeclared access blocked at runtime |
| Prompt injection via read content | Untrusted-content tagging; injected instructions cannot grant capabilities; risky-action gate requires user confirm |
| Self-learned bad behavior | Promotion gates, brain PRs, full revert; lessons cannot expand capabilities, only strategy |
| No enterprise visibility | Action ledger export, fleet inventory beacon (opt-in), remote kill |
| Credential sprawl | Secrets vault, per-skill scoped tokens, never placed in model context |

Stance in docs and marketing: we publish our threat model and invite audits pre-1.0. After OpenClaw's 2026, "secure by default" is a feature users actively shop for.

---

## 7. MVP Definition (v0.1 — "Minimum Lovable Agent")

**Platform:** Linux (incl. WSL2). **Interface:** CLI + Telegram. **Language:** Python (genome already built and tested) with a thin TypeScript option deferred.

**In scope:**
1. Gateway daemon + CLI channel + Telegram channel
2. Agent loop with shell, file, web-fetch tools in a sandbox; deny-all permission prompts
3. Compiled context engine (no transcript replay)
4. Model router with 3 tiers + per-task receipts
5. Genome v1: record → learn → serve → close-loop; teach-and-it-sticks; `tars brain`, `brain log`, `brain revert`, `forget`
6. Doorman v1: cron + file-watch + IMAP IDLE triggers, local-model gatekeeping
7. Action ledger + kill switch
8. Sunday Self-Review message
9. `tars eval` A/B harness

**Explicitly out of scope for v0.1:** browser automation, WhatsApp, multi-agent orchestration, decision simulator, federated learning, Windows-native, mobile apps.

**Definition of done:** a new user reaches the Minute-5 brain moment in under 5 minutes; idle cost < ₹1/day; an eval on a 200-task suite shows statistically meaningful lift from lessons; zero critical findings from an external security review of defaults.

---

## 8. Roadmap

| Version | Theme | Highlights |
|---|---|---|
| v0.1 | Minimum Lovable Agent | Everything in §7 |
| v0.2 | Trust at depth | Browser tool (sandboxed), conflict detection UI, signed skill format + manifest validator, prompt-injection red-team suite |
| v0.3 | Compounding | Skill Darwinism (per-skill scoreboards, retirement), long-horizon Objective Engine (persistent goals, heartbeat-free scheduling), WhatsApp/Slack |
| v0.4 | Teams | Fleet inventory, remote kill, shared team genomes with role-scoped lessons, SSO |
| v0.5 | Network effects | Opt-in federated genome: anonymized, evidence-validated lessons shared across deployments — every user's failures teach every user's agent |

---

## 9. Success Metrics

**Activation:** % of installs reaching the Minute-5 brain moment (target: >60%).
**Magic-moment proxy:** brain-dashboard screenshots / social shares per 100 installs.
**Retention:** % of agents still receiving events at day 30 (target: >40%).
**Trust:** lesson approval rate; revert rate (healthy: low but non-zero — zero means nobody's looking).
**Economy:** median idle cost/day (<₹1); median ₹ saved by routing per active user-week.
**Compounding (north star):** median task success rate at week 8 vs week 1 per user, from the built-in eval — the number no competitor can publish.

---

## 10. Go-to-Market (launch sequence)

1. **Proof post:** publish the eval — "same agent, 500 tasks, +X% success with the genome, receipts included." Data posts are what the community now rewards; hype posts are penalized.
2. **Show HN / r/LocalLLaMA:** lead with the brain: "My agent reports what it learned each week, with evidence, and I can revert its mind like git."
3. **The migration wedge:** an OpenClaw/Hermes importer (`tars import`) that ingests their Markdown memory/skills as *candidate* lessons — instantly useful to the two largest agent communities, and a living demo of "your old agent's notes, now with evidence."
4. **The cost story:** side-by-side receipt comparison vs documented OpenClaw bills.
5. **Security posture:** publish threat model + invite audit before 1.0; contrast with the incumbents' 2026 record without naming-and-shaming.

---

## 11. Risks & Open Questions (honest section)

- **Extraction quality:** if proposed lessons are trivial or wrong too often, brain PRs become noise. Mitigation: batch extraction, contrast-based promotion, aggressive dedup, and a "quiet brain" setting.
- **Latency of trust features:** permission prompts and gates add friction; the deny-all UX must be one-tap and remembered, or users will blanket-approve (recreating P1).
- **Incumbent speed:** Hermes could bolt on lesson versioning. Our moat is the evidence model + eval harness + receipts as identity, not a feature checkbox — move fast on the experience.
- **Local-model dependence:** the Doorman assumes a competent tiny model; needs graceful degradation to cheap-API-only setups.
- **Honest limits:** no architecture makes an agent infallible; TARS bounds and surfaces failure rather than promising its absence. We never market "no mistakes" — we market *visible, reversible, cheaper* mistakes.

---

## 12. Glossary

- **Genome** — the versioned store of validated lessons, failure models, and their evidence.
- **Lesson / Heuristic** — a scoped, falsifiable behavioral rule with Bayesian confidence.
- **Brain PR** — a candidate lesson awaiting evidence or user approval.
- **Episode** — one recorded task execution; the atomic unit of experience.
- **Doorman** — the event-driven, low-cost wake layer replacing heartbeat polling.
- **Compiled context** — the per-turn minimal context assembled from structured state instead of replayed history.
- **Receipt** — the per-task cost/model/duration summary.
- **Sunday Self-Review** — the weekly growth report of tasks, lessons, and savings.

---

*"Agents that remember were version one. TARS is the agent that grows — and shows its work."*
