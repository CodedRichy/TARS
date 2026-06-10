-- TARS Genome schema: episodes, heuristics, evidence, failure models, changelog

CREATE TABLE IF NOT EXISTS episode (
    id              TEXT PRIMARY KEY,
    goal            TEXT NOT NULL,
    context_features TEXT NOT NULL DEFAULT '{}',
    action_trace    TEXT NOT NULL DEFAULT '[]',
    outcome         TEXT NOT NULL,
    outcome_detail  TEXT,
    lessons_applied TEXT NOT NULL DEFAULT '[]',
    failure_models_checked TEXT NOT NULL DEFAULT '[]',
    cost_breakdown  TEXT NOT NULL DEFAULT '{}',
    started_at      TEXT NOT NULL,
    completed_at    TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_episode_outcome ON episode(outcome);
CREATE INDEX IF NOT EXISTS idx_episode_completed ON episode(completed_at);

CREATE TABLE IF NOT EXISTS heuristic (
    id              TEXT PRIMARY KEY,
    statement       TEXT NOT NULL,
    scope           TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'CANDIDATE',
    supporting      REAL NOT NULL DEFAULT 0,
    contradicting   REAL NOT NULL DEFAULT 0,
    confidence      REAL NOT NULL DEFAULT 0.5,
    origin_type     TEXT NOT NULL DEFAULT 'EXTRACTED',
    origin_episode_id TEXT,
    promoted_at     TEXT,
    deprecated_at   TEXT,
    last_applied_at TEXT,
    last_evidence_at TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_heuristic_status ON heuristic(status);
CREATE INDEX IF NOT EXISTS idx_heuristic_confidence ON heuristic(confidence);

CREATE TABLE IF NOT EXISTS evidence (
    id              TEXT PRIMARY KEY,
    heuristic_id    TEXT NOT NULL REFERENCES heuristic(id),
    episode_id      TEXT NOT NULL REFERENCES episode(id),
    direction       TEXT NOT NULL,
    weight          REAL NOT NULL DEFAULT 1.0,
    reasoning       TEXT,
    is_origin       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_heuristic ON evidence(heuristic_id);
CREATE INDEX IF NOT EXISTS idx_evidence_episode ON evidence(episode_id);

CREATE TABLE IF NOT EXISTS failure_model (
    id              TEXT PRIMARY KEY,
    signature       TEXT NOT NULL,
    root_cause      TEXT NOT NULL,
    recovery_path   TEXT NOT NULL DEFAULT '[]',
    scope           TEXT NOT NULL DEFAULT '{}',
    trigger_count   INTEGER NOT NULL DEFAULT 1,
    last_triggered_at TEXT,
    source_episodes TEXT NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_fm_status ON failure_model(status);

CREATE TABLE IF NOT EXISTS changelog (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    hash            TEXT NOT NULL UNIQUE,
    prev_hash       TEXT NOT NULL,
    timestamp       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    entity_type     TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    operation       TEXT NOT NULL,
    field_changes   TEXT NOT NULL DEFAULT '{}',
    reason          TEXT,
    snapshot        TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_changelog_entity ON changelog(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_changelog_timestamp ON changelog(timestamp);
