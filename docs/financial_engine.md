# AGCI Financial Engine: PostgreSQL S-Curve Logic

This document outlines the technical implementation of the construction cash flow forecasting engine, which has been migrated from Python to a reactive PL/pgSQL implementation within the PostgreSQL database.

## 1. Overview

The Financial Engine is responsible for generating a non-linear "S-curve" distribution of capital over a project's lifecycle. It operates as a **reactive system**: any change to a project's timeline or budget automatically triggers a recalculation of the monthly cash flow profile.

## 2. Mathematical Foundation

The engine uses a **Rational Polynomial Function (5th Order)** to model the cumulative capital deployment. This specific model is chosen for its ability to accurately reflect the three phases of construction:
1.  **Early Ramp-up** (Mobilization & Design)
2.  **Peak Spend** (Structural & Major MEP works)
3.  **Wind-down** (Finishes, Commissioning, & Closeout)

### Coefficients
The S-curve is defined by the following constants:

| Coefficient | Value |
| :--- | :--- |
| **A** | 0.707205007505421 |
| **B** | -0.0667363632084369 |
| **C** | 0.0104156261597405 |
| **D** | 0.00174018878670432 |
| **E** | -0.00125942062519033 |
| **F** | -0.0000219638781679794 |
| **G** | 0.0000116670093891432 |
| **H** | 1.35120107553353e-7 |
| **I** | 1.21646666783187e-7 |
| **J** | -3.14406828446384e-10 |

### Function: `fn_calculate_s_curve_pct(x)`
Input `x` is the percentage of time elapsed (0–120).
The function returns the cumulative percentage of capital deployed.

```sql
num := A + C*x + E*x^2 + G*x^3 + I*x^4;
den := 1 + B*x + D*x^2 + F*x^3 + H*x^4 + J*x^5;
RETURN num / den;
```

## 3. Database Implementation

### Reactive Trigger: `trg_recalculate_cashflow`
The engine is initialized by a database trigger on the `projects` table. It fires **AFTER INSERT OR UPDATE** specifically on the following columns:
- `start_date`
- `end_date`
- `total_capital`

### Procedure: `pr_recalculate_cashflow()`
This procedure performs the following steps when a project is modified:
1.  **Cleanup**: Deletes existing records in `cashflow_monthly` and `project_summary` for the project.
2.  **Validation**: Ensures the project has valid dates and budget.
3.  **Duration Calculation**: Computes the baseline duration and extends it by 20% (to handle the closeout tail).
4.  **Monthly Loop**:
    *   Iterates month-by-month.
    *   Calculates `pct_of_time`.
    *   Calls `fn_calculate_s_curve_pct` to get `cum_pct`.
    *   Calculates period spend and phase (`early`, `peak`, `wind_down`).
    *   Inserts results into `cashflow_monthly`.
5.  **Snapshotting**: Records the Peak Spend Date and the Half-Capital (50%) Date in `project_summary`.

## 4. Data Structures

### Table: `cashflow_monthly`
Stores the granular time-series data used for dashboard charts.
- `month_number`: Sequential month index (0, 1, 2...).
- `month_start`: The calendar date for the period.
- `cashflow`: The absolute currency amount spent in that month.
- `cum_pct`: The S-curve progress percentage.

### Table: `project_summary`
Stores pre-calculated KPIs for high-performance filtering and reporting.
- `peak_monthly_spend`: The highest single-month expenditure.
- `half_capital_date`: The "Midpoint of Investment".

## 5. Usage in API

Because the math is handled at the database layer, the FastAPI backend (`main.py`) remains extremely lightweight. To fetch a project's cash flow, the API simply runs:

```sql
SELECT * FROM cashflow_monthly WHERE project_id = $1 ORDER BY month_number;
```

This architecture ensures that intelligence discovered by AGCI agents is immediately available for financial analysis without requiring manual intervention or separate batch processing jobs.
