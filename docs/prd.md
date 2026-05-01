# Autonomous Global Construction Intelligence (AGCI) — Product Requirements Document

**Version:** 2.0  
**Date:** May 2026  
**Status:** Production Ready (Autonomous)

---

## 1. Overview

This document describes the design, implementation, and deployment of the **Autonomous Global Construction Intelligence (AGCI)** system. AGCI is an integrated platform that autonomously discovers global construction projects and models their monthly capital expenditure profiles using a high-precision rational polynomial S-curve engine.

The system combines a multi-agent AI research pipeline (AGCI Auditor) with a reactive financial forecasting engine built directly into a shared PostgreSQL core.

---

## 2. Background & Problem Statement

Construction project data is often fragmented, stale, and difficult to forecast. 

**Goals:**
1.  **Autonomous Discovery:** Use AI agents to sweep global markets and identify construction projects, stakeholders, and budgets.
2.  **Self-Healing Data:** Automatically audit and verify project metadata (dates, capital) to eliminate "Unknown" values.
3.  **Reactive Forecasting:** Immediately generate financial profiles (S-curves) the moment a project is discovered or updated, using a unified database source of truth.

---

## 3. The Financial Engine

The cash flow curve is defined by a **rational polynomial** implemented directly in PL/pgSQL for maximum performance and consistency.

**Key Features:**
- **In-DB Processing:** Calculations are triggered automatically by PostgreSQL whenever a project's timeline or budget changes.
- **Safety Floors:** The engine includes NULL checks and a 0.1-month minimum duration floor to ensure resilience against incomplete or extreme project data.
- **Tail extension:** Automatically extends forecasts to 120% of nominal duration to account for closeout costs.
- **Milestone Trend Analysis (MTA):** Automatically identifies key capital deployment milestones (10%, 25%, 50%, 75%, 90%, 100%).

---

## 4. System Architecture

```
┌──────────────────────────┐        ┌──────────────────────────────┐
│   Browser (index.html)   │  HTTP  │   FastAPI (main.py)          │
│                          │◄──────►│                              │
│  - Real-time Dashboard   │        │  - SQL-driven API            │
│  - Regional Intelligence │        │  - Persisted Data Endpoints  │
└─────────────┬────────────┘        └──────────────┬───────────────┘
              │                                    │
              │             ┌──────────────────────▼┐
              │             │  PostgreSQL Cluster   │
              │             │  (Shared Source)      │
              │             ├───────────────────────┤
              └────────────►│ - Reactive Triggers   │◄────────────┐
                            │ - S-Curve Logic (SQL) │             │
                            │ - Safety Floors       │             │
                            └───────────────────────┘             │
                                       ▲                          │
                                       │                  ┌───────┴───────┐
                                       │                  │ AGCI Auditor  │
                                       └──────────────────┤ (AI Agents)   │
                                                          └───────────────┘
```

**Infrastructure Features:**
- **Unified Core:** The Dashboard and AGCI Auditor share the same PostgreSQL instance.
- **Threaded Connection Pooling:** Managed via `ConnectionPoolManager` (min=1, max=20) for high-concurrency multi-agent auditing.
- **Reactive Triggers:** Project updates from AGCI automatically fire financial recalculations with safety guards.

---

## 5. Components

### 5.1 AGCI Auditor (Intelligence Layer)
- **Multi-Agent Loop:** Research agents discover projects and stakeholders.
- **Data Healing:** Automatically resolves missing dates and budgets via web search grounding.
- **Regional Round-Robin:** Distributes API load across global regions to maximize quota.

### 5.2 PostgreSQL Core (Persistence & Processing)
- **Reactive Trigger:** `trg_recalculate_cashflow` fires on project updates.
- **S-Curve Function:** `fn_calculate_s_curve_pct` provides high-precision polynomial math.
- **Views:** `v_projects_summary` and `v_cashflow_annual` provide real-time reporting.

### 5.3 Cash Flow Dashboard (Presentation Layer)
- **FastAPI Backend:** Provides a high-performance REST API over the PostgreSQL views.
- **Persisted Forecasts:** A dedicated endpoint (`/api/projects/{id}/cashflow`) allows the UI to fetch pre-calculated forecasts directly from the DB.
- **Interactive UI:** Chart.js visualizations for S-curves and Milestone Trend Analysis.

---

## 6. Project File Structure

```
project-agent/           # Intelligence Engine
├── src/agci/
│   ├── memory.py        # Connection Pool & Storage Logic
│   ├── nodes/           # AI Agent nodes (Auditor, Architect)
│   └── cli.py           # Command Line Interface
└── .env                 # Database & API configuration

cashflow/                # Presentation & API Layer
├── main.py              # FastAPI app
├── schema.sql           # Database schema + PL/pgSQL Engine
└── static/
    └── index.html       # Web frontend
```

---

## 7. Deployment & Operations

- **Platform:** Render.com (Web Services + Managed PostgreSQL).
- **Persistence:** Full PostgreSQL storage with indexed retrieval for 700+ projects.
- **Scalability:** Threaded connection pooling (min=1, max=20) supports parallel auditing.

---

## 8. Known Limitations & Roadmap

| Item | Description |
|------|-------------|
| **Multi-Curve Support** | Future: Implement sector-specific coefficients (e.g. Infrastructure vs. Residential). |
| **Milestone Logic** | Current: MTA is calculated in SQL. Future: Surface drift alerts in the UI. |

| **Auth & Security** | Future: Implement OAuth2 for regional analyst access. |
| **Excel Sync** | Future: Bi-directional sync with legacy `.xlsx` trackers. |

---

## 9. API Endpoints

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/api/projects` | List all projects with summaries (paginated) |
| `GET` | `/api/projects/{id}/cashflow` | Fetch persisted S-curve & milestones for a specific project |
| `GET` | `/api/cashflow` | On-the-fly calculation via query parameters |
| `GET` | `/api/health` | Service health and database status |


---

*Document revised for Autonomous Production — May 2026*