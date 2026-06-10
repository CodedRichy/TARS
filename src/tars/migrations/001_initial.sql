-- TARS v0.1 initial schema
-- Foundation tables for permissions and action ledger

CREATE TABLE IF NOT EXISTS permissions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    capability  TEXT NOT NULL,
    scope       TEXT NOT NULL,
    granted_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    expires_at  TEXT,
    granted_by  TEXT NOT NULL DEFAULT 'user',
    revoked_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_permissions_capability ON permissions(capability);
CREATE INDEX IF NOT EXISTS idx_permissions_active ON permissions(revoked_at) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS action_ledger (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    prev_hash   TEXT NOT NULL,
    timestamp   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    session_id  TEXT NOT NULL,
    tool        TEXT NOT NULL,
    action      TEXT NOT NULL,
    plan_step   TEXT,
    result      TEXT,
    hash        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ledger_session ON action_ledger(session_id);
CREATE INDEX IF NOT EXISTS idx_ledger_timestamp ON action_ledger(timestamp);
