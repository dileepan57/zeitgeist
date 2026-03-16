-- Migration 002: Telemetry, Evals, and Simulator tables
-- Run this in Supabase SQL Editor after 001_initial_schema.sql

-- ============================================================
-- TELEMETRY TABLES
-- ============================================================

-- Per-run collector health tracking
CREATE TABLE IF NOT EXISTS collector_runs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID REFERENCES daily_runs(id) ON DELETE CASCADE,
    collector_name  TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('success', 'partial', 'blocked', 'error')),
    items_collected INTEGER DEFAULT 0,
    duration_ms INTEGER,
    error_msg   TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_collector_runs_run_id ON collector_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_collector_runs_collector ON collector_runs(collector_name);
CREATE INDEX IF NOT EXISTS idx_collector_runs_created ON collector_runs(created_at DESC);

-- Historical snapshots of signal performance (taken at each weekly calibration)
CREATE TABLE IF NOT EXISTS signal_perf_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_source   TEXT NOT NULL,
    precision       FLOAT,
    recall          FLOAT,
    true_positives  INTEGER DEFAULT 0,
    false_positives INTEGER DEFAULT 0,
    true_negatives  INTEGER DEFAULT 0,
    false_negatives INTEGER DEFAULT 0,
    snapshot_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sig_perf_hist_source ON signal_perf_history(signal_source);
CREATE INDEX IF NOT EXISTS idx_sig_perf_hist_date ON signal_perf_history(snapshot_date DESC);

-- Claude API usage tracking
CREATE TABLE IF NOT EXISTS claude_usage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID REFERENCES daily_runs(id) ON DELETE SET NULL,
    call_type       TEXT NOT NULL, -- 'gap_analysis', 'opportunity_brief', 'app_fit', 'knowledge', 'eval'
    topic           TEXT,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    duration_ms     INTEGER,
    cost_usd        FLOAT DEFAULT 0.0,
    success         BOOLEAN DEFAULT TRUE,
    error_msg       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_claude_usage_run_id ON claude_usage(run_id);
CREATE INDEX IF NOT EXISTS idx_claude_usage_created ON claude_usage(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_claude_usage_call_type ON claude_usage(call_type);

-- ============================================================
-- EVALS TABLES
-- ============================================================

-- Eval run results (one row per metric per eval run)
CREATE TABLE IF NOT EXISTS eval_results (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_name   TEXT NOT NULL,    -- 'consistency', 'calibration', 'gap_analysis', 'opportunity_brief', 'app_fit'
    run_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    metric_name TEXT NOT NULL,    -- 'std_dev', 'brier_score', 'specificity', 'coherence', etc.
    metric_value FLOAT,
    threshold   FLOAT,            -- what counts as passing
    passed      BOOLEAN,
    details     JSONB,            -- additional context
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_results_name ON eval_results(eval_name);
CREATE INDEX IF NOT EXISTS idx_eval_results_date ON eval_results(run_date DESC);

-- ============================================================
-- SIMULATOR TABLES
-- ============================================================

-- Simulator scenario run results
CREATE TABLE IF NOT EXISTS simulation_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_date        DATE NOT NULL DEFAULT CURRENT_DATE,
    scenario_name   TEXT NOT NULL,
    scenario_type   TEXT,
    input_signals   JSONB,
    actual_output   JSONB,
    expected_outcome JSONB,
    passed          BOOLEAN,
    failure_reason  TEXT,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sim_runs_date ON simulation_runs(run_date DESC);
CREATE INDEX IF NOT EXISTS idx_sim_runs_scenario ON simulation_runs(scenario_name);
CREATE INDEX IF NOT EXISTS idx_sim_runs_passed ON simulation_runs(passed);

-- ============================================================
-- VIEWS
-- ============================================================

-- Collector health summary: last 7 days per collector
CREATE OR REPLACE VIEW collector_health AS
SELECT
    collector_name,
    COUNT(*) AS total_runs,
    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successes,
    SUM(CASE WHEN status IN ('blocked', 'error') THEN 1 ELSE 0 END) AS failures,
    ROUND(100.0 * SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) / COUNT(*), 1) AS success_rate_pct,
    AVG(duration_ms) AS avg_duration_ms,
    AVG(items_collected) AS avg_items,
    MAX(created_at) AS last_run
FROM collector_runs
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY collector_name
ORDER BY success_rate_pct ASC;

-- Claude cost summary by day
CREATE OR REPLACE VIEW claude_daily_cost AS
SELECT
    DATE(created_at) AS date,
    SUM(total_tokens) AS total_tokens,
    SUM(cost_usd) AS total_cost_usd,
    COUNT(*) AS api_calls,
    COUNT(CASE WHEN success = FALSE THEN 1 END) AS errors
FROM claude_usage
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- Latest eval results per eval type
CREATE OR REPLACE VIEW latest_evals AS
SELECT DISTINCT ON (eval_name, metric_name)
    eval_name,
    metric_name,
    metric_value,
    threshold,
    passed,
    run_date,
    details
FROM eval_results
ORDER BY eval_name, metric_name, run_date DESC;

-- Simulator pass rate summary
CREATE OR REPLACE VIEW simulator_summary AS
SELECT
    scenario_name,
    COUNT(*) AS total_runs,
    SUM(CASE WHEN passed THEN 1 ELSE 0 END) AS passes,
    SUM(CASE WHEN NOT passed THEN 1 ELSE 0 END) AS failures,
    MAX(run_date) AS last_run,
    BOOL_AND(passed) AS currently_passing
FROM simulation_runs
GROUP BY scenario_name
ORDER BY scenario_name;
