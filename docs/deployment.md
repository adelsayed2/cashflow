# Deployment Process

This document outlines the standard workflow for deploying updates to the **Cashflow** project, covering both code (GitHub) and data (Render Production).

## 1. Local Development & Verification
Before deploying, ensure the local environment is stable:
- **Start Database**: `./db.sh up`
- **Start Server**: `./venv/bin/python -m uvicorn main:app --reload --port 8000`
- **Verify UI**: Navigate to `http://localhost:8000` and check for console errors.

## 2. Code Deployment (GitHub)
Pushing to the `main` branch triggers the Render web service build process (if configured for auto-deploy).

```bash
git add .
git commit -m "feat: description of changes"
git push origin main
```

## 3. Database Deployment (Render)
The database on Render is updated by dumping the local Docker PostgreSQL state and uploading it to the Render instance. This is managed by the `push_to_render.sh` script.

### Prerequisites
- **Docker**: The `cashflow-db` container must be running.
- **Environment**: The `.env` file must contain a valid `REMOTE_DATABASE_URL` (or `INTERNAL_DATABASE_URL`).

### Execution
Run the following command:
```bash
./push_to_render.sh
```
*Note: This script will ask for confirmation before overwriting the production database.*

### What the script does:
1. Extracts the remote database URL from `.env`.
2. Uses `docker exec` to run `pg_dump` inside the local container.
3. Streams the dump directly to the remote Render PostgreSQL instance via `psql`.
4. Recreates all triggers and functions (Reactive Engine) on the production server.

## 4. Post-Deployment Checks
1. Check the **Render Dashboard** for build status.
2. Visit the production URL.
3. Test a project profile (e.g., `/profile.html?id=...`) to ensure the API and database are in sync.
