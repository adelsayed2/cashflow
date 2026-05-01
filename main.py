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
    version="1.1.2",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

def get_db_conn():
    # If on Render, prefer Internal URL. If local, prefer public DATABASE_URL.
    is_render = os.getenv("RENDER") is not None
    db_url = None
    
    if is_render:
        db_url = os.getenv("INTERNAL_DATABASE_URL") or os.getenv("DATABASE_URL")
    else:
        db_url = os.getenv("DATABASE_URL") or os.getenv("INTERNAL_DATABASE_URL")
    
    if not db_url:
        logger.error("No database URL found in environment variables.")
        return None
    
    try:
        # On Render, external connections usually need sslmode=require
        conn_str = db_url
        if "render.com" in conn_str and "sslmode" not in conn_str:
            separator = "&" if "?" in conn_str else "?"
            conn_str += f"{separator}sslmode=require"
            
        # Add a connect_timeout to prevent hanging the server on connection issues
        return psycopg2.connect(conn_str, cursor_factory=RealDictCursor, connect_timeout=5)
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
    
    milestones_def = [
        {"id": "M1", "name": "Mobilisation", "threshold": 10},
        {"id": "M2", "name": "Quarter capital", "threshold": 25},
        {"id": "M3", "name": "Half capital", "threshold": 50},
        {"id": "M4", "name": "Three-quarter", "threshold": 75},
        {"id": "M5", "name": "Practical compl.", "threshold": 90},
        {"id": "M6", "name": "Final closeout", "threshold": 100},
    ]
    
    milestones = []
    for m_def in milestones_def:
        target = m_def["threshold"]
        m_row = next((r for r in rows if r["cum_pct"] >= target - 0.001), rows[-1])
        milestones.append({
            "id": m_def["id"],
            "name": m_def["name"],
            "threshold": f"{m_def['threshold']}% capital",
            "target_date": m_row["month_start"][:7],
            "month_number": f"M{m_row['month_number']}",
            "capital_deployed": m_row["cum_cashflow"],
            "phase": m_row["phase"]
        })

    return summary, rows, milestones

@app.get("/api/health", tags=["health"])
def health():
    db_url = os.getenv("DATABASE_URL")
    internal_url = os.getenv("INTERNAL_DATABASE_URL")
    
    return {
        "status": "ok", 
        "version": "1.1.2", 
        "db_url_present": db_url is not None,
        "internal_url_present": internal_url is not None,
        "db_url_preview": f"{db_url[:15]}..." if db_url else None,
        "environment": "render" if os.getenv("RENDER") else "local"
    }

@app.get("/api/projects", tags=["projects"])
def get_projects(limit: int = 50, offset: int = 0):
    conn = get_db_conn()
    if not conn:
        db_url = os.getenv("DATABASE_URL")
        internal_url = os.getenv("INTERNAL_DATABASE_URL")
        is_render = os.getenv("RENDER") is not None
        
        detail = "Database connection failed. "
        if not db_url and not internal_url:
            detail += "Missing environment variables (DATABASE_URL/INTERNAL_DATABASE_URL)."
        elif not is_render:
            detail += "Local connection attempt timed out. Check if your IP is whitelisted on Render's Access Control or if you are using the correct External Database URL."
        else:
            detail += "Internal connection failed. Check Render's service logs."
            
        raise HTTPException(status_code=503, detail=detail)

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

@app.get("/api/projects/{project_id}/cashflow", tags=["projects"])
def get_project_cashflow(project_id: str):
    conn = get_db_conn()
    if not conn:
        raise HTTPException(status_code=503, detail="Database connection failed")

    try:
        cur = conn.cursor()
        
        # 1. Fetch Summary
        cur.execute("SELECT * FROM v_projects_summary WHERE id = %s", (project_id,))
        summary = cur.fetchone()
        if not summary:
            raise HTTPException(status_code=404, detail="Project not found")

        # 2. Fetch Monthly Data
        cur.execute("SELECT * FROM cashflow_monthly WHERE project_id = %s ORDER BY month_number", (project_id,))
        monthly = cur.fetchall()

        # 3. Calculate Milestones (thresholds)
        milestones_def = [
            {"id": "M1", "name": "Mobilisation", "threshold": 10},
            {"id": "M2", "name": "Quarter capital", "threshold": 25},
            {"id": "M3", "name": "Half capital", "threshold": 50},
            {"id": "M4", "name": "Three-quarter", "threshold": 75},
            {"id": "M5", "name": "Practical compl.", "threshold": 90},
            {"id": "M6", "name": "Final closeout", "threshold": 100},
        ]
        
        milestones = []
        for m_def in milestones_def:
            target = m_def["threshold"]
            m_row = next((r for r in monthly if r["cum_pct"] >= target - 0.001), monthly[-1] if monthly else None)
            if m_row:
                milestones.append({
                    "id": m_def["id"],
                    "name": m_def["name"],
                    "threshold": f"{m_def['threshold']}% capital",
                    "target_date": m_row["month_start"].isoformat()[:7] if hasattr(m_row["month_start"], 'isoformat') else str(m_row["month_start"])[:7],
                    "month_number": f"M{m_row['month_number']}",
                    "capital_deployed": float(m_row["cum_cashflow"]),
                    "phase": m_row["phase"]
                })

        cur.close()
        conn.close()
        
        # Convert summary to match _compute_cashflow structure for frontend compatibility
        formatted_summary = {
            "project_name":       summary["project_name"],
            "start_date":         summary["start_date"].isoformat(),
            "end_date":           summary["end_date"].isoformat(),
            "duration_months":    float(summary["duration_months"]),
            "effective_months":   summary.get("effective_months", len(monthly)-1),
            "total_capital":      float(summary["total_capital"]),
            "currency":           summary["currency"],
            "peak_monthly_spend": float(summary["peak_monthly_spend"]) if summary["peak_monthly_spend"] else 0,
            "peak_month_number":  summary["peak_month_number"],
            "peak_month_date":    summary["peak_month_date"].isoformat() if summary["peak_month_date"] else None,
            "half_capital_month": summary["half_capital_month"],
            "half_capital_date":  summary["half_capital_date"].isoformat() if summary["half_capital_date"] else None,
        }

        # Format monthly rows
        formatted_monthly = []
        for r in monthly:
            formatted_monthly.append({
                "month_number": r["month_number"],
                "month_start":  r["month_start"].isoformat(),
                "pct_of_time":  float(r["pct_of_time"]),
                "cum_pct":      float(r["cum_pct"]),
                "period_pct":   float(r["period_pct"]),
                "cashflow":     float(r["cashflow"]),
                "cum_cashflow": float(r["cum_cashflow"]),
                "phase":        r["phase"]
            })

        return JSONResponse({"summary": formatted_summary, "monthly": formatted_monthly, "milestones": milestones})
    except Exception as e:
        if conn: conn.close()
        logger.error(f"Cashflow detail error: {e}")
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
        summary, rows, milestones = _compute_cashflow(start_date, end_date, total_capital, currency)
        summary["project_name"] = project_name
        return JSONResponse({"summary": summary, "monthly": rows, "milestones": milestones})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

@app.post("/api/cashflow", tags=["cashflow"])
def post_cashflow(body: CashFlowRequest):
    try:
        summary, rows, milestones = _compute_cashflow(
            body.start_date, body.end_date, body.total_capital, body.currency
        )
        summary["project_name"] = body.project_name
        return JSONResponse({"summary": summary, "monthly": rows, "milestones": milestones})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

# Serve frontend
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
