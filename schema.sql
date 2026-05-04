-- ============================================================
-- AGCI Autonomous Construction Intelligence — Unified Schema
-- PostgreSQL
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Projects ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
    id              UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id          VARCHAR(50),
    project_name    TEXT        NOT NULL,
    description     TEXT,
    city            VARCHAR(100),
    country         VARCHAR(100),
    site            TEXT,
    sector          VARCHAR(50),
    status          VARCHAR(50),
    funding_type    VARCHAR(50),
    developer       TEXT,
    main_contractor TEXT,
    architect       TEXT,
    pmc             TEXT,
    mep_contractor  TEXT,
    structural_engineer TEXT,
    capacity        INTEGER,
    capacity_unit   VARCHAR(50),
    size_sqm        INTEGER,
    budget_value_local DECIMAL(20, 2),
    currency        VARCHAR(10) DEFAULT 'USD',
    total_capital   NUMERIC(20, 2), -- normalized USD
    start_date      DATE,
    end_date        DATE,
    contract_award_date DATE,
    duration_months NUMERIC(10, 2),
    sources         JSONB,
    tags            JSONB,
    x_links         JSONB,
    last_audited    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Monthly Cash Flow ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cashflow_monthly (
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
CREATE TABLE IF NOT EXISTS project_summary (
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
CREATE INDEX IF NOT EXISTS idx_cashflow_project_id     ON cashflow_monthly(project_id);
CREATE INDEX IF NOT EXISTS idx_cashflow_month_number   ON cashflow_monthly(project_id, month_number);
CREATE INDEX IF NOT EXISTS idx_projects_created_at     ON projects(created_at DESC);

-- ── S-Curve Financial Engine (PL/pgSQL) ─────────────────────────

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
    -- 1. Cleanup
    DELETE FROM cashflow_monthly WHERE project_id = NEW.id;
    DELETE FROM project_summary WHERE project_id = NEW.id;

    -- 2. Validate
    IF NEW.end_date IS NULL OR NEW.start_date IS NULL OR NEW.end_date <= NEW.start_date OR NEW.total_capital IS NULL OR NEW.total_capital <= 0 THEN
        RETURN NEW;
    END IF;

    -- 3. Calculate Core Metrics
    v_duration_months := (EXTRACT(YEAR FROM NEW.end_date) - EXTRACT(YEAR FROM NEW.start_date)) * 12 + 
                         (EXTRACT(MONTH FROM NEW.end_date) - EXTRACT(MONTH FROM NEW.start_date)) + 
                         (EXTRACT(DAY FROM NEW.end_date) - EXTRACT(DAY FROM NEW.start_date)) / 30.0;
    v_duration_months := GREATEST(0.1, v_duration_months);
    
    -- Update the project duration field (non-recursively)
    UPDATE projects SET duration_months = v_duration_months WHERE id = NEW.id;

    v_total_months := (v_duration_months * 1.20)::INTEGER + 1;

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

        IF v_cashflow > v_peak_value THEN
            v_peak_value := v_cashflow; v_peak_date := v_month_date; v_peak_month_num := v_m;
        END IF;

        IF v_half_cap_date IS NULL AND v_cum_pct >= 50 THEN
            v_half_cap_date := v_month_date; v_half_cap_month := v_m;
        END IF;

        v_prev_cum := v_cum_pct;
        EXIT WHEN v_pct_of_time >= 120.0;
    END LOOP;

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