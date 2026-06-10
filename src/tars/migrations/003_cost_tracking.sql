-- Cost receipts and daily budget tracking

CREATE TABLE IF NOT EXISTS cost_receipt (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    session_id      TEXT,
    episode_id      TEXT,
    tier            TEXT NOT NULL,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    prompt_tokens   INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    cost_inr        REAL NOT NULL DEFAULT 0.0,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    task_class      TEXT,
    stakes          TEXT
);

CREATE INDEX IF NOT EXISTS idx_receipt_timestamp ON cost_receipt(timestamp);
CREATE INDEX IF NOT EXISTS idx_receipt_session ON cost_receipt(session_id);
CREATE INDEX IF NOT EXISTS idx_receipt_episode ON cost_receipt(episode_id);

CREATE TABLE IF NOT EXISTS daily_budget (
    date            TEXT PRIMARY KEY,
    spent_inr       REAL NOT NULL DEFAULT 0.0,
    limit_inr       REAL NOT NULL DEFAULT 50.0,
    receipt_count   INTEGER NOT NULL DEFAULT 0
);
