# TARS

An AI agent framework in Python for people who want an assistant with persistent memory that talks to them over Telegram, email, an HTTP API or the terminal.

## What it does

- Keeps what it learns about you in a SQLite store (the "genome"), so it remembers across restarts.
- Takes messages from the CLI, Telegram, an IMAP inbox trigger and a FastAPI gateway.
- Checks every request in a "doorman" layer (auth, rate limiting) before it reaches the agent.
- Runs tools, and can connect to MCP servers through its MCP client.
- Tracks its own performance over time (`tars curves`, `tars digest`) and ships an eval harness (`tars eval`).
- Includes `tars doctor` for self-diagnostics.

```
You (Telegram / Email / API / CLI)
        |
   Doorman (auth) -> Router (intent) -> Agent (LiteLLM)
                                          |
                          Tools      Genome      Curves
                        (actions)   (memory)   (learning)
```

## Status

Working, pre-1.0. 306 test functions across unit, integration and end-to-end suites. The roadmap items not done yet: web dashboard for the genome, voice channel, multi-agent collaboration, embedding-based memory, plugin marketplace.

## Stack

Python 3.11+, LiteLLM, Typer and Rich, FastAPI and Uvicorn, aiosqlite, python-telegram-bot, imapclient, Pydantic.

## Run it

```bash
git clone https://github.com/CodedRichy/TARS.git
cd TARS
pip install -e ".[dev]"
tars chat      # terminal chat
tars start     # start the daemon and channels
pytest tests/ -v
docker compose up -d
```

You need an API key for any provider LiteLLM supports (OpenAI, Anthropic, Groq, Ollama and others).

## Project structure

```
src/tars/
  agent/      agent loop, planner, permissions
  channels/   CLI and Telegram adapters
  cli/        Typer commands
  core/       config, database, events, logging
  curves/     performance snapshots and digest
  doctor/     health checks and fixes
  doorman/    auth, rate limiting, triggers (including IMAP)
  eval/       evaluation harness
  gateway/    FastAPI HTTP API and daemon
  genome/     persistent memory
  mcp/        MCP client and bridge
  review/     Sunday review
  router/     intent routing
  tools/      tool system
tests/        unit, integration, e2e
```

## Contributing

Issues and pull requests are welcome. Run `pytest tests/` before opening a PR.

## License

MIT. See LICENSE.
