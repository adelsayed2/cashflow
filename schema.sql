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
    s.effective_months,
    s.peak_monthly_spend,
    s.peak_month_number,
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


-- ── S-Curve Financial Engine (PL/pgSQL) ─────────────────────────

-- High-precision rational polynomial S-curve calculation
CREATE OR REPLACE FUNCTION fn_calculate_s_curve_pct(x NUMERIC)
RETURNS NUMERIC AS $$
DECLARE
    _A NUMERIC :=  0.707205007505421;
    _B NUMERIC := -0.0667363632084369;
    _C NUMERIC :=  0.0104156261597405;
    _D NUMERIC :=  0.00174018878670432;
    _E NUMERIC := -0.00125942062519033;
    _F NUMERIC := -0.0000219638781679794;
    _G NUMERIC :=  0.0000116670093891432;
    _H NUMERIC :=  1.35120107553353e-7;
    _I NUMERIC :=  1.21646666783187e-7;
    _J NUMERIC := -3.14406828446384e-10;
    num NUMERIC;
    den NUMERIC;
    res NUMERIC;
BEGIN
    num := _A + _C*x + _E*power(x,2) + _G*power(x,3) + _I*power(x,4);
    den := 1  + _B*x + _D*power(x,2) + _F*power(x,3) + _H*power(x,4) + _J*power(x,5);
    res := num / den;
    RETURN GREATEST(0.0, LEAST(100.0, res));
END;
$$ LANGUAGE plpgsql;

-- Procedure to regenerate all forecasts for a project
CREATE OR REPLACE FUNCTION pr_recalculate_cashflow()
RETURNS TRIGGER AS $$
DECLARE
    v_duration_months NUMERIC;
    v_total_months INTEGER;
    v_m INTEGER;
    v_month_date DATE;
    v_pct_of_time NUMERIC;
    v_cum_pct NUMERIC;
    v_period_pct NUMERIC;
    v_prev_cum NUMERIC := 0.0;
    v_cashflow NUMERIC;
    v_cum_cf NUMERIC;
    v_phase TEXT;
    v_peak_value NUMERIC := 0.0;
    v_peak_date DATE;
    v_peak_month_num INTEGER;
    v_half_cap_date DATE;
    v_half_cap_month INTEGER;
BEGIN
    -- 1. Cleanup existing calculations
    DELETE FROM cashflow_monthly WHERE project_id = NEW.id;
    DELETE FROM project_summary WHERE project_id = NEW.id;

    -- 2. Validate inputs
    IF NEW.end_date IS NULL OR NEW.start_date IS NULL OR NEW.end_date <= NEW.start_date OR NEW.total_capital IS NULL OR NEW.total_capital <= 0 THEN
        RETURN NEW;
    END IF;

    -- 3. Calculate core metrics
    v_duration_months := (EXTRACT(YEAR FROM NEW.end_date) - EXTRACT(YEAR FROM NEW.start_date)) * 12 + 
                         (EXTRACT(MONTH FROM NEW.end_date) - EXTRACT(MONTH FROM NEW.start_date)) + 
                         (EXTRACT(DAY FROM NEW.end_date) - EXTRACT(DAY FROM NEW.start_date)) / 30.0;
    
    -- Ensure duration is at least 0.1 months to avoid division errors
    v_duration_months := GREATEST(0.1, v_duration_months);
    
    -- Update the project duration field
    UPDATE projects SET duration_months = v_duration_months WHERE id = NEW.id;

    v_total_months := (v_duration_months * 1.20)::INTEGER + 1;
    
    -- Safety check for total months
    IF v_total_months IS NULL OR v_total_months < 0 THEN
        v_total_months := 1;
    END IF;

    -- 4. Generate Monthly Cash Flow
    FOR v_m IN 0..v_total_months LOOP
        v_month_date := NEW.start_date + (v_m || ' months')::INTERVAL;
        v_pct_of_time := LEAST((v_m / v_duration_months) * 100.0, 120.0);
        v_cum_pct := fn_calculate_s_curve_pct(v_pct_of_time);
        v_period_pct := GREATEST(0.0, v_cum_pct - v_prev_cum);
        v_cashflow := ROUND((NEW.total_capital * v_period_pct / 100.0), 2);
        v_cum_cf := ROUND((NEW.total_capital * v_cum_pct / 100.0), 2);
        
        v_phase := CASE 
            WHEN v_pct_of_time <= 40 THEN 'early'
            WHEN v_pct_of_time <= 80 THEN 'peak'
            ELSE 'wind_down'
        END;

        INSERT INTO cashflow_monthly (
            project_id, month_number, month_start, pct_of_time, 
            cum_pct, period_pct, cashflow, cum_cashflow, phase
        ) VALUES (
            NEW.id, v_m, v_month_date, v_pct_of_time, 
            v_cum_pct, v_period_pct, v_cashflow, v_cum_cf, v_phase
        );

        -- Track summary metrics
        IF v_cashflow > v_peak_value THEN
            v_peak_value := v_cashflow;
            v_peak_date := v_month_date;
            v_peak_month_num := v_m;
        END IF;

        IF v_half_cap_date IS NULL AND v_cum_pct >= 50 THEN
            v_half_cap_date := v_month_date;
            v_half_cap_month := v_m;
        END IF;

        v_prev_cum := v_cum_pct;
        EXIT WHEN v_pct_of_time >= 120.0;
    END LOOP;

    -- 5. Insert Summary Snapshot
    INSERT INTO project_summary (
        project_id, effective_months, peak_monthly_spend, 
        peak_month_number, peak_month_date, half_capital_month, half_capital_date
    ) VALUES (
        NEW.id, v_total_months, v_peak_value, 
        v_peak_month_num, v_peak_date, v_half_cap_month, v_half_cap_date
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ── Reactive Financial Trigger ───────────────────────────────

-- Fire the financial engine after any project data update
DROP TRIGGER IF EXISTS trg_recalculate_cashflow ON projects;
CREATE TRIGGER trg_recalculate_cashflow
    AFTER INSERT OR UPDATE OF start_date, end_date, total_capital
    ON projects
    FOR EACH ROW
    EXECUTE FUNCTION pr_recalculate_cashflow();