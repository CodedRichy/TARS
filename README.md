<div align="center">

# TARS

**The first AI agent with a brain you can watch grow.**

A self-improving AI agent framework with persistent memory, multi-channel communication, and a learning loop that gets smarter with every interaction.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-306+-22c55e?style=flat-square)](#testing)

</div>

---

## What It Does

TARS is an AI agent that remembers, learns, and operates across multiple channels -- Telegram, email (IMAP), HTTP API, and MCP. Unlike stateless chatbots, TARS maintains a persistent genome of learned behaviors, routes tasks through specialized tools, and continuously self-evaluates to improve.

```
You (Telegram / Email / API / MCP)
        │
        ▼
   ┌─────────┐     ┌──────────┐     ┌──────────┐
   │ Doorman  │────▶│  Router  │────▶│  Agent   │
   │ (Auth)   │     │ (Intent) │     │ (LiteLLM)│
   └─────────┘     └──────────┘     └────┬─────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
              ┌──────────┐       ┌──────────┐        ┌──────────┐
              │  Tools   │       │  Genome  │        │  Curves  │
              │ (Actions)│       │ (Memory) │        │ (Learn)  │
              └──────────┘       └──────────┘        └──────────┘
```

## Key Features

- **Multi-Channel** -- Telegram bot, email inbox monitoring (IMAP), HTTP API gateway, and MCP server. One agent, every surface.
- **Persistent Genome** -- Learned behaviors, preferences, and context stored in SQLite. The agent remembers across restarts.
- **Learning Curves** -- Self-evaluation loop that tracks performance and adjusts behavior over time.
- **Tool System** -- Extensible plugin architecture for custom actions.
- **Doorman Auth** -- Request validation and rate limiting before anything reaches the agent.
- **Smart Router** -- Intent classification that routes messages to the right handler without explicit commands.
- **Doctor** -- Self-diagnostics and health monitoring.
- **Eval Harness** -- Built-in evaluation framework to measure agent quality.

## Quick Start

### Prerequisites

- Python 3.11+
- An LLM API key (any provider supported by [LiteLLM](https://docs.litellm.ai/))

### Install

```bash
git clone https://github.com/CodedRichy/TARS.git
cd TARS
pip install -e ".[dev]"
```

### Run

```bash
# CLI mode
tars chat

# Start all channels
tars serve
```

## Architecture

```
src/tars/
  agent/        Core agent loop and LLM interaction
  channels/     Telegram, email (IMAP), HTTP adapters
  cli/          Typer CLI interface
  core/         Config, logging, base classes
  curves/       Learning loop and self-improvement
  doctor/       Self-diagnostics and health checks
  doorman/      Authentication and rate limiting
  eval/         Evaluation harness
  gateway/      FastAPI HTTP API server
  genome/       Persistent memory (SQLite)
  mcp/          Model Context Protocol server
  router/       Intent classification and routing
  tools/        Extensible tool/plugin system
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Runtime** | Python 3.11+ |
| **LLM** | LiteLLM (any provider -- OpenAI, Anthropic, Groq, Ollama) |
| **CLI** | Typer + Rich |
| **API** | FastAPI + Uvicorn |
| **Database** | aiosqlite (async SQLite) |
| **Telegram** | python-telegram-bot |
| **Email** | imapclient |
| **Scheduling** | croniter + watchdog |
| **Validation** | Pydantic |

## Testing

```bash
pytest tests/ -v
```

306+ tests across unit, integration, and end-to-end suites.

## Docker

```bash
docker compose up -d
```

## Roadmap

- [ ] Web dashboard for genome visualization
- [ ] Voice channel (Twilio)
- [ ] Multi-agent collaboration
- [ ] Embeddings-powered semantic memory
- [ ] Plugin marketplace

## License

[MIT](LICENSE)

---

<div align="center">

Built by [Rishi Praseeth Krishnan](https://rishipraseeth.in)

</div>
