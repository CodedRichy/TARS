-- Improvement snapshots for tracking TARS growth over time

CREATE TABLE IF NOT EXISTS improvement_snapshot (
    id              TEXT PRIMARY KEY,
    period_type     TEXT NOT NULL,  -- daily, weekly, monthly
    period_label    TEXT NOT NULL,  -- 2026-06-05, 2026-W23, 2026-06
    taken_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),

    -- Task metrics
    total_episodes      INTEGER NOT NULL DEFAULT 0,
    success_count       INTEGER NOT NULL DEFAULT 0,
    partial_count       INTEGER NOT NULL DEFAULT 0,
    failure_count       INTEGER NOT NULL DEFAULT 0,
    success_rate        REAL NOT NULL DEFAULT 0.0,

    -- Brain metrics
    total_lessons       INTEGER NOT NULL DEFAULT 0,
    active_lessons      INTEGER NOT NULL DEFAULT 0,
    candidate_lessons   INTEGER NOT NULL DEFAULT 0,
    promoted_count      INTEGER NOT NULL DEFAULT 0,  -- promoted this period
    reverted_count      INTEGER NOT NULL DEFAULT 0,  -- reverted this period
    avg_confidence      REAL NOT NULL DEFAULT 0.0,
    p50_confidence      REAL NOT NULL DEFAULT 0.0,
    p90_confidence      REAL NOT NULL DEFAULT 0.0,

    -- Cost metrics
    total_cost_inr      REAL NOT NULL DEFAULT 0.0,
    cost_per_task       REAL NOT NULL DEFAULT 0.0,
    cost_per_success    REAL NOT NULL DEFAULT 0.0,

    -- Growth score (composite 0-100)
    growth_score        REAL NOT NULL DEFAULT 0.0,

    -- Deltas vs previous snapshot of same period_type
    delta_success_rate  REAL,
    delta_growth_score  REAL,
    delta_active_lessons INTEGER,
    delta_cost_per_task REAL,

    UNIQUE(period_type, period_label)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_period ON improvement_snapshot(period_type, period_label);
CREATE INDEX IF NOT EXISTS idx_snapshot_taken ON improvement_snapshot(taken_at);
