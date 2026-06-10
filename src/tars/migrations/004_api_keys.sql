CREATE TABLE IF NOT EXISTS api_key (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    key_hash    TEXT NOT NULL UNIQUE,
    scopes      TEXT NOT NULL DEFAULT '["*"]',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_used   TEXT,
    revoked     INTEGER NOT NULL DEFAULT 0
);
