# Local Database Sync Report

This document outlines the architecture and operation of the local data synchronization pipeline between the **AGCI Intelligence Database (SQLite)** and the **Cashflow Application (PostgreSQL/Docker)**.

## 🏗️ Architecture Overview

The sync operation is a multi-stage ETL (Extract, Transform, Load) process designed to transform raw construction data into cashflow-optimized project records.

- **Source**: `/Users/adelsayed/Documents/code/project-agent/data/agci.db` (SQLite)
- **Destination**: `localhost:5432/cashflow_local` (PostgreSQL in Docker)

## 🔄 Sync Pipeline Stages

### 1. Data Migration (`migrate_sqlite.py`)
Extracts project data from SQLite and maps it to the PostgreSQL schema.
- **Budget Logic**: Prioritizes `budget_value_usd` but falls back to `budget_value` if the USD value is missing.
- **Date Normalization**: 
  - `YYYY-MM-DD` is parsed normally.
  - `YYYY-MM` is normalized to the 1st of the month.
  - `YYYY` is normalized to January 1st of that year.
- **Validation**:
  - Projects with `Unknown` dates are skipped (mathematically required for S-Curves).
  - Projects with invalid ranges (Start >= End) are assigned a **minimum 1-month duration** to ensure they appear in the database.

### 2. Metrics Refresh (`refresh_summaries.py`)
Once data is migrated, this script runs the core S-Curve rational polynomial formula for every project.
- **Project Summaries**: Populates `project_summary` with peak spend, peak dates, and half-capital milestones.
- **Monthly Cashflows**: Generates month-by-month spend projections in `cashflow_monthly`.
- **Performance**: Uses PostgreSQL `UPSERT` (ON CONFLICT) and `execute_values` for high-speed batch processing.

## 📊 Current Statistics (As of May 1, 2026)

| Metric | Value |
| :--- | :--- |
| **Total Projects Found in Source** | 2,165 |
| **Cashflow-Optimized Candidates** | 316 |
| **Successfully Migrated & Processed** | **317** (includes test/manual entries) |
| **Monthly Periods Generated** | 18,158 |
| **Skipped (Missing Dates)** | 71 |

## 🛠️ Management Commands

We have centralized all operations in the `./db.sh` helper script:

| Command | Description |
| :--- | :--- |
| `./db.sh up` | Start the local PostgreSQL Docker container |
| `./db.sh sync` | **Run the full sync pipeline** (Migrate + Refresh) |
| `./db.sh push` | **Push local data to Render (Production)** |
| `./db.sh shell` | Open a psql terminal into the local DB |

| `./db.sh logs` | View database logs |
| `./db.sh down` | Stop the local database |

## 📝 Configuration

The system uses the following environment variables in `.env`:
- `SOURCE_SQLITE_DB`: Path to the agci.db file.
- `DATABASE_URL`: Set to the local Docker Postgres URL for development.
