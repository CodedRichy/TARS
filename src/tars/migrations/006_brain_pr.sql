-- Brain PR system: review/approve/reject lesson promotions

CREATE TABLE IF NOT EXISTS brain_pr (
    pr_number       INTEGER PRIMARY KEY AUTOINCREMENT,
    heuristic_id    TEXT NOT NULL REFERENCES heuristic(id),
    status          TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING, APPROVED, REJECTED
    reason          TEXT,
    resolved_by     TEXT,  -- user, auto
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    resolved_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_brain_pr_status ON brain_pr(status);
CREATE INDEX IF NOT EXISTS idx_brain_pr_heuristic ON brain_pr(heuristic_id);
