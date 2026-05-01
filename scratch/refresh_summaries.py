import os
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from dotenv import load_dotenv
from main import _compute_cashflow
from datetime import date

load_dotenv()

POSTGRES_URL = os.getenv("DATABASE_URL")

def refresh():
    print(f"Connecting to Postgres: {POSTGRES_URL}")
    conn = psycopg2.connect(POSTGRES_URL, cursor_factory=RealDictCursor)
    cur = conn.cursor()
    
    # 1. Fetch all projects
    cur.execute("SELECT id, project_name, start_date, end_date, total_capital, currency FROM projects")
    projects = cur.fetchall()
    print(f"Processing {len(projects)} projects...")
    
    summary_data = []
    cashflow_rows = []
    
    for p in projects:
        try:
            summary, rows, milestones = _compute_cashflow(
                p['start_date'], p['end_date'], float(p['total_capital']), p['currency']
            )
            
            summary_data.append((
                p['id'],
                summary['effective_months'],
                summary['peak_monthly_spend'],
                summary['peak_month_number'],
                summary['peak_month_date'],
                summary['half_capital_month'],
                summary['half_capital_date']
            ))
            
            for r in rows:
                cashflow_rows.append((
                    p['id'],
                    r['month_number'],
                    r['month_start'],
                    r['pct_of_time'],
                    r['cum_pct'],
                    r['period_pct'],
                    r['cashflow'],
                    r['cum_cashflow'],
                    r['phase']
                ))
        except Exception as e:
            print(f"Error processing {p['project_name']}: {e}")

    # 2. Insert Summaries
    print(f"Inserting {len(summary_data)} summaries...")
    summary_query = """
        INSERT INTO project_summary 
            (project_id, effective_months, peak_monthly_spend, peak_month_number, peak_month_date, half_capital_month, half_capital_date)
        VALUES %s
        ON CONFLICT (project_id) DO UPDATE SET
            effective_months = EXCLUDED.effective_months,
            peak_monthly_spend = EXCLUDED.peak_monthly_spend,
            peak_month_number = EXCLUDED.peak_month_number,
            peak_month_date = EXCLUDED.peak_month_date,
            half_capital_month = EXCLUDED.half_capital_month,
            half_capital_date = EXCLUDED.half_capital_date
    """
    execute_values(cur, summary_query, summary_data)
    
    # 3. Insert Cashflow (optional but good for views)
    print(f"Inserting {len(cashflow_rows)} cashflow months...")
    # Clear old cashflow to avoid duplicates if not using UPSERT
    cur.execute("DELETE FROM cashflow_monthly WHERE project_id IN %s", (tuple(p['id'] for p in projects),))
    
    cf_query = """
        INSERT INTO cashflow_monthly 
            (project_id, month_number, month_start, pct_of_time, cum_pct, period_pct, cashflow, cum_cashflow, phase)
        VALUES %s
    """
    execute_values(cur, cf_query, cashflow_rows)
    
    conn.commit()
    print("Refresh complete!")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    refresh()
