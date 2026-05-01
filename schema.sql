-- ============================================================
-- Construction Cash Flow — Database Schema
-- PostgreSQL
-- ============================================================

-- ── Extensions ───────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Projects ─────────────────────────────────────────────────
-- One row per construction project
CREATE TABLE projects (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_name    TEXT        NOT NULL,
    start_date      DATE        NOT NULL,
    end_date        DATE        NOT NULL,
    total_capital   NUMERIC(20, 2) NOT NULL,
    currency        VARCHAR(10) NOT NULL DEFAULT 'USD',
    duration_months NUMERIC(6, 2),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Monthly Cash Flow ─────────────────────────────────────────
-- One row per month per project (output of the S-curve formula)
CREATE TABLE cashflow_monthly (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id      UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    month_number    INTEGER     NOT NULL,
    month_start     DATE        NOT NULL,
    pct_of_time     NUMERIC(8, 4) NOT NULL,
    cum_pct         NUMERIC(8, 4) NOT NULL,
    period_pct      NUMERIC(8, 4) NOT NULL,
    cashflow        NUMERIC(20, 2) NOT NULL,
    cum_cashflow    NUMERIC(20, 2) NOT NULL,
    phase           VARCHAR(20) NOT NULL CHECK (phase IN ('early', 'peak', 'wind_down')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Summary Snapshots ─────────────────────────────────────────
-- Stores the computed summary metrics per project
CREATE TABLE project_summary (
    id                  UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id          UUID        NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    effective_months    INTEGER,
    peak_monthly_spend  NUMERIC(20, 2),
    peak_month_number   INTEGER,
    peak_month_date     DATE,
    half_capital_month  INTEGER,
    half_capital_date   DATE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────
CREATE INDEX idx_cashflow_project_id     ON cashflow_monthly(project_id);
CREATE INDEX idx_cashflow_month_number   ON cashflow_monthly(project_id, month_number);
CREATE INDEX idx_cashflow_phase          ON cashflow_monthly(phase);
CREATE INDEX idx_projects_created_at     ON projects(created_at DESC);

-- ── Auto-update updated_at ────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Useful Views ──────────────────────────────────────────────

-- Project list with summary joined
CREATE VIEW v_projects_summary AS
SELECT
    p.id,
    p.project_name,
    p.start_date,
    p.end_date,
    p.total_capital,
    p.currency,
    p.duration_months,
    s.peak_monthly_spend,
    s.peak_month_date,
    s.half_capital_month,
    s.half_capital_date,
    p.created_at
FROM projects p
LEFT JOIN project_summary s ON s.project_id = p.id
ORDER BY p.created_at DESC;

-- Annual cash flow rollup per project
CREATE VIEW v_cashflow_annual AS
SELECT
    project_id,
    EXTRACT(YEAR FROM month_start)::INTEGER AS year,
    SUM(cashflow)       AS annual_cashflow,
    SUM(cum_cashflow)   AS cum_cashflow_at_year_end,
    MIN(phase)          AS dominant_phase
FROM cashflow_monthly
GROUP BY project_id, EXTRACT(YEAR FROM month_start)
ORDER BY project_id, year;