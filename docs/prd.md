# Construction Cash Flow S-Curve — Product Requirements Document

**Version:** 1.0  
**Date:** May 2026  
**Status:** MVP Complete  

---

## 1. Overview

This document describes the design, implementation, and deployment of the **Construction Cash Flow S-Curve Tool** — a web-based application that models and visualises the monthly capital expenditure profile of a construction project using a rational polynomial S-curve formula.

The tool is intended for project managers, cost engineers, and finance teams who need to forecast monthly cash drawdowns during the construction phase of capital projects (e.g. oil & gas, infrastructure, real estate).

---

## 2. Background & Problem Statement

Construction projects do not spend capital evenly over time. Expenditure follows a characteristic S-shape:

- **Early phase** — slow ramp-up (mobilisation, design, site preparation)
- **Mid phase** — peak spend (civil works, bulk procurement, equipment installation)
- **Late phase** — gradual wind-down (commissioning, testing, snagging, closeout)

Manually modelling this curve month-by-month is time-consuming and error-prone. The existing tool (an Excel workbook — `Cash_flow_calc_NEW_XLS.xlsx`) applied a rational polynomial formula to automate this calculation, but was limited to a single project at a time and not accessible to non-Excel users.

**Goal:** Expose the same formula as a reusable API with an interactive web frontend, deployable to the cloud.

---

## 3. The Formula

The cash flow curve is defined by a **rational polynomial** — a polynomial numerator divided by a polynomial denominator — which provides the flexibility to model the asymmetric spend shape of real construction projects.

```
y = (a + cx + ex² + gx³ + ix⁴)
    ───────────────────────────────────────────
    (1 + bx + dx² + fx³ + hx⁴ + jx⁵)
```

Where:

| Coefficient | Value |
|-------------|-------|
| a | 0.707205007505421 |
| b | −0.0667363632084369 |
| c | 0.0104156261597405 |
| d | 0.00174018878670432 |
| e | −0.00125942062519033 |
| f | −0.0000219638781679794 |
| g | 0.0000116670093891432 |
| h | 1.35120107553353 × 10⁻⁷ |
| i | 1.21646666783187 × 10⁻⁷ |
| j | −3.14406828446384 × 10⁻¹⁰ |

**Input variable:**  
`x` = percentage of project time elapsed, where:
- `0%` = construction start date (sanction / FID)
- `100%` = planned completion / RFO date

**Key rule:** 100% of the cash flow is only reached at **120% of time**, not at 100%. This accounts for tail costs — commissioning, punch-list closeout, demobilisation, and documentation — which extend spending beyond the nominal end date.

**Output:**  
`y` = cumulative percentage of total capital spent at time `x`

Monthly period spend is derived by differencing successive cumulative values.

---

## 4. System Architecture

```
┌─────────────────────────┐        ┌──────────────────────────────┐
│   Browser (index.html)  │  HTTP  │   FastAPI (main.py)           │
│                         │◄──────►│                              │
│  - Date / capital inputs│        │  GET /api/cashflow           │
│  - Chart.js S-curve     │        │  POST /api/cashflow          │
│  - Monthly data table   │        │  GET /api/health             │
│  - CSV export           │        │                              │
└─────────────────────────┘        │  Serves /static → index.html│
                                   └──────────────────────────────┘
                                              │
                                    ┌─────────▼──────────┐
                                    │   Render.com        │
                                    │   (Python web svc)  │
                                    └────────────────────┘
```

Everything is served from a single Render web service:
- The FastAPI backend handles all `/api/*` routes
- The `static/` folder containing `index.html` is mounted at `/` and served directly by FastAPI

---

## 5. Components

### 5.1 Python Core Function — `cashflow_monthly()`

**File:** `main.py` (also portable as a standalone module)

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `start` | `date` | Construction start date |
| `end` | `date` | Planned completion / RFO date |
| `total_capital` | `float` | Total project capital (End-of-Job cost) |
| `currency` | `str` | Currency label (e.g. USD, AED, GBP) |

**Output:** A row per month containing:

| Field | Description |
|-------|-------------|
| `month_number` | 0-based month index |
| `month_start` | ISO date of the first day of that month |
| `pct_of_time` | `x` value fed into the formula (0 → 120) |
| `cum_pct` | Cumulative % of capital spent |
| `period_pct` | % of capital spent in this month |
| `cashflow` | Actual monetary spend this month |
| `cum_cashflow` | Cumulative spend to date |
| `phase` | `early` / `peak` / `wind_down` |

**Duration calculation:** Fractional months using actual calendar dates via `python-dateutil`, correctly handling varying month lengths.

**Tail extension:** The function automatically extends the schedule to 120% of the nominal duration — no manual input required.

---

### 5.2 FastAPI Backend — `main.py`

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/cashflow` | Calculate via query parameters |
| `POST` | `/api/cashflow` | Calculate via JSON body |
| `GET` | `/docs` | Auto-generated Swagger UI |

**GET `/api/cashflow` query parameters:**

| Parameter | Required | Default | Example |
|-----------|----------|---------|---------|
| `start_date` | Yes | — | `2022-01-01` |
| `end_date` | Yes | — | `2025-09-01` |
| `total_capital` | Yes | — | `100000000` |
| `currency` | No | `USD` | `AED` |
| `project_name` | No | `null` | `Oryx GTL` |

**Example response:**

```json
{
  "summary": {
    "project_name": "Oryx GTL",
    "start_date": "2022-01-01",
    "end_date": "2025-09-01",
    "duration_months": 44.03,
    "effective_months": 53,
    "total_capital": 100000000,
    "currency": "USD",
    "peak_monthly_spend": 4950000,
    "peak_month_number": 32,
    "peak_month_date": "2024-09-01",
    "half_capital_month": 27,
    "half_capital_date": "2024-04-01"
  },
  "monthly": [
    {
      "month_number": 1,
      "month_start": "2022-02-01",
      "pct_of_time": 2.27,
      "cum_pct": 0.845,
      "period_pct": 0.845,
      "cashflow": 845263.0,
      "cum_cashflow": 845263.0,
      "phase": "early"
    }
  ]
}
```

---

### 5.3 Frontend — `static/index.html`

A single self-contained HTML file served by FastAPI. No build step or framework required.

**Features:**

- Project name, start date, end date, total capital, and currency inputs
- Live API URL preview bar showing the exact GET request being made
- Summary metric cards: total capital, duration, peak monthly spend, 50% deployment date
- Interactive S-curve chart (Chart.js) with:
  - Monthly spend bars colour-coded by phase (early / peak / wind-down)
  - Cumulative spend line on a dual Y-axis
  - Hover tooltips showing monetary values
- Full monthly data table with phase badges
- One-click CSV export

**Technology:** Vanilla HTML/CSS/JS + Chart.js 4.4.1 (CDN). No framework, no build tooling.

---

## 6. Project File Structure

```
cashflow_app/
├── main.py              # FastAPI app — API logic + static file serving
├── requirements.txt     # Python dependencies
├── render.yaml          # Render deployment config
└── static/
    └── index.html       # Web frontend (served at /)
```

---

## 7. Dependencies

**Python:**

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | ≥ 0.110.0 | API framework |
| `uvicorn[standard]` | ≥ 0.29.0 | ASGI server |
| `python-dateutil` | ≥ 2.9.0 | Fractional month calculation |
| `pydantic` | ≥ 2.0.0 | Request validation |

**Frontend (CDN):**

| Library | Version | Purpose |
|---------|---------|---------|
| Chart.js | 4.4.1 | S-curve and bar chart |
| Google Fonts | — | Syne + DM Mono typefaces |

---

## 8. Deployment — Render.com

**Service type:** Web Service (Python)  
**Build command:** `pip install -r requirements.txt`  
**Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`  
**Runtime:** Python 3.11

**`render.yaml`** is included in the repo — Render auto-detects it and pre-fills all configuration. Deployment is triggered automatically on every push to the connected GitHub branch.

**Live URLs (once deployed):**

| Path | Description |
|------|-------------|
| `https://your-app.onrender.com/` | Web frontend |
| `https://your-app.onrender.com/api/cashflow?...` | JSON API |
| `https://your-app.onrender.com/docs` | Swagger UI |

> **Note:** Render free-tier services spin down after 15 minutes of inactivity. The first request after idle takes ~30 seconds. Use a paid plan ($7/month) for always-on availability.

---

## 9. Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Start the API server
uvicorn main:app --reload
# → http://localhost:8000

# Open the frontend
open static/index.html
# or visit http://localhost:8000/ directly
```

**Test the API:**
```bash
curl "http://localhost:8000/api/cashflow?start_date=2022-01-01&end_date=2025-09-01&total_capital=100000000&currency=USD"
```

**Interactive API docs:**
```
http://localhost:8000/docs
```

---

## 10. Phase Definitions

| Phase | Time range (% of duration) | Characteristics |
|-------|---------------------------|-----------------|
| Early | 0% – 40% | Slow ramp-up. Mobilisation, design finalisation, site prep. |
| Peak | 40% – 80% | Maximum monthly spend. Civil works, bulk procurement, major equipment. |
| Wind-down | 80% – 120% | Tapering spend. Commissioning, testing, snagging, final closeout. |

---

## 11. Known Limitations & Future Enhancements

| Item | Description |
|------|-------------|
| Single S-curve | The formula uses fixed coefficients calibrated to a specific project type. Projects with unusual spend profiles (e.g. heavily front-loaded procurement) may not be accurately modelled. |
| No authentication | The API is currently open. For production use with sensitive project data, add API key or OAuth authentication. |
| No persistence | Project inputs are not saved between sessions. A database layer (PostgreSQL on Render) could store named projects. |
| Single currency display | Currency is a label only — no exchange rate conversion. |
| Free-tier cold starts | Render free tier has ~30s cold start latency after inactivity. |
| Multi-project dashboard | Future: allow side-by-side comparison of multiple projects on one chart. |
| Excel export | Future: export the monthly table directly to `.xlsx` using the existing Python function with `openpyxl`. |

---

## 12. Reference Files

| File | Description |
|------|-------------|
| `Cash_Flow_Formula_copy.docx` | Source document containing the rational polynomial formula and coefficients |
| `Cash_flow_calc_NEW_XLS.xlsx` | Original Excel implementation (Oryx GTL, 44-month, $100M project) |

---

*Document prepared from session outputs — May 2026*