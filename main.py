from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import date
from dateutil.relativedelta import relativedelta
from pydantic import BaseModel
from typing import Optional, List
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(
    title="Construction Cash Flow API",
    description="S-curve rational polynomial cash flow calculator and project manager",
    version="1.1.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Prioritize Internal URL for Render-to-Render communication
DATABASE_URL = os.getenv("INTERNAL_DATABASE_URL") or os.getenv("DATABASE_URL")

def get_db_conn():
    if not DATABASE_URL:
        logger.error("DATABASE_URL not found in environment variables.")
        return None
    try:
        # On Render, external connections usually need sslmode=require
        # We can append it if it's a render.com host and not already present
        conn_str = DATABASE_URL
        if "render.com" in conn_str and "sslmode" not in conn_str:
            separator = "&" if "?" in conn_str else "?"
            conn_str += f"{separator}sslmode=require"
            
        return psycopg2.connect(conn_str, cursor_factory=RealDictCursor)
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

_A =  0.707205007505421
_B = -0.0667363632084369
_C =  0.0104156261597405
_D =  0.00174018878670432
_E = -0.00125942062519033
_F = -0.0000219638781679794
_G =  0.0000116670093891432
_H =  1.35120107553353e-7
_I =  1.21646666783187e-7
_J = -3.14406828446384e-10

def _cumulative_pct(x: float) -> float:
    num = _A + _C*x + _E*x**2 + _G*x**3 + _I*x**4
    den = 1  + _B*x + _D*x**2 + _F*x**3 + _H*x**4 + _J*x**5
    return max(0.0, min(100.0, num / den))

def _compute_cashflow(start: date, end: date, total_capital: float, currency: str):
    if end <= start:
        raise ValueError("end date must be after start date")

    duration_months = (
        (end.year - start.year) * 12 + (end.month - start.month)
        + (end.day - start.day) / 30.0
    )

    total_months = int(duration_months * 1.20) + 1
    rows = []
    prev_cum = 0.0
    peak_month = None
    peak_value = 0.0

    for m in range(total_months + 1):
        month_date = start + relativedelta(months=m)
        pct_of_time = min((m / duration_months) * 100.0, 120.0)
        cum_pct    = _cumulative_pct(pct_of_time)
        period_pct = max(0.0, cum_pct - prev_cum)
        cashflow   = round(total_capital * period_pct / 100.0, 2)
        cum_cf     = round(total_capital * cum_pct / 100.0, 2)

        row = {
            "month_number":  m,
            "month_start":   month_date.isoformat(),
            "pct_of_time":   round(pct_of_time, 4),
            "cum_pct":       round(cum_pct, 4),
            "period_pct":    round(period_pct, 4),
            "cashflow":      cashflow,
            "cum_cashflow":  cum_cf,
            "phase": (
                "early"     if pct_of_time <= 40 else
                "peak"      if pct_of_time <= 80 else
                "wind_down"
            ),
        }
        rows.append(row)
        if cashflow > peak_value:
            peak_value = cashflow
            peak_month = row
        prev_cum = cum_pct
        if pct_of_time >= 120.0:
            break

    mid50 = next((r for r in rows if r["cum_pct"] >= 50), rows[-1])
    summary = {
        "project_name":       None,
        "start_date":         start.isoformat(),
        "end_date":           end.isoformat(),
        "duration_months":    round(duration_months, 2),
        "effective_months":   total_months,
        "total_capital":      total_capital,
        "currency":           currency,
        "peak_monthly_spend": round(peak_value, 2),
        "peak_month_number":  peak_month["month_number"] if peak_month else None,
        "peak_month_date":    peak_month["month_start"]  if peak_month else None,
        "half_capital_month": mid50["month_number"],
        "half_capital_date":  mid50["month_start"],
    }
    return summary, rows

class CashFlowRequest(BaseModel):
    start_date:    date
    end_date:      date
    total_capital: float
    currency:      Optional[str] = "USD"
    project_name:  Optional[str] = None

@app.get("/api/health", tags=["health"])
def health():
    return {
        "status": "ok", 
        "version": "1.1.1", 
        "db_configured": DATABASE_URL is not None,
        "environment": "render" if os.getenv("RENDER") else "local"
    }

@app.get("/api/projects", tags=["projects"])
def get_projects(limit: int = 50, offset: int = 0):
    conn = get_db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database connection failed. Ensure DATABASE_URL is set in Render Dashboard.")
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM v_projects_summary LIMIT %s OFFSET %s", (limit, offset))
        projects = cur.fetchall()
        cur.close()
        conn.close()
        return projects
    except Exception as e:
        if conn: conn.close()
        logger.error(f"Query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cashflow", tags=["cashflow"])
def get_cashflow(
    start_date:    date  = Query(...),
    end_date:      date  = Query(...),
    total_capital: float = Query(...),
    currency:      str   = Query("USD"),
    project_name:  str   = Query(None),
):
    try:
        summary, rows = _compute_cashflow(start_date, end_date, total_capital, currency)
        summary["project_name"] = project_name
        return JSONResponse({"summary": summary, "monthly": rows})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

@app.post("/api/cashflow", tags=["cashflow"])
def post_cashflow(body: CashFlowRequest):
    try:
        summary, rows = _compute_cashflow(
            body.start_date, body.end_date, body.total_capital, body.currency
        )
        summary["project_name"] = body.project_name
        return JSONResponse({"summary": summary, "monthly": rows})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

# Serve frontend
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
