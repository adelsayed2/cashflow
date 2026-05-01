import os
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from datetime import datetime
import uuid

load_dotenv()

SQLITE_PATH = os.getenv("SOURCE_SQLITE_DB")
POSTGRES_URL = os.getenv("DATABASE_URL")

def migrate():
    print(f"Connecting to SQLite: {SQLITE_PATH}")
    sl_conn = sqlite3.connect(SQLITE_PATH)
    sl_cur = sl_conn.cursor()
    
    print(f"Connecting to Postgres: {POSTGRES_URL}")
    pg_conn = psycopg2.connect(POSTGRES_URL)
    pg_cur = pg_conn.cursor()
    
    # Perform a Clean Slate Sync: Wiping existing PG data to eliminate duplicates
    print("Performing Clean Slate Sync: Truncating projects table...")
    pg_cur.execute("TRUNCATE projects CASCADE;")
    pg_conn.commit()

    # Fetch data from SQLite
    # We strictly use budget_value_usd and force currency to USD
    sl_cur.execute("""
        SELECT 
            project_id, 
            name, 
            start_date, 
            completion_date, 
            budget_value_usd 
        FROM projects 
        WHERE name IS NOT NULL AND name != ''
          AND start_date IS NOT NULL AND start_date != ''
          AND completion_date IS NOT NULL AND completion_date != ''
          AND budget_value_usd IS NOT NULL AND budget_value_usd > 0
    """)

    
    rows = sl_cur.fetchall()
    print(f"Found {len(rows)} valid projects in SQLite.")
    
    data_to_insert = []
    skipped_count = 0
    
    for row in rows:
        p_id, name, start, end, budget = row
        
        def parse_date(d_str):
            if not d_str or d_str.lower() == 'unknown':
                return None
            try:
                if len(d_str) == 10: # YYYY-MM-DD
                    return datetime.strptime(d_str, '%Y-%m-%d')
                elif len(d_str) == 7: # YYYY-MM
                    return datetime.strptime(d_str, '%Y-%m')
                elif len(d_str) == 4: # YYYY
                    return datetime.strptime(d_str, '%Y')
            except:
                return None
            return None

        d1 = parse_date(start)
        d2 = parse_date(end)
        
        if not d1 or not d2:
            print(f"Skipping {name}: Missing/Unknown dates (Start: {start}, End: {end})")
            skipped_count += 1
            continue
            
        # Validate duration - if start >= end, force 1 month duration instead of skipping
        duration = (d2.year - d1.year) * 12 + (d2.month - d1.month)
        if duration <= 0:
            from dateutil.relativedelta import relativedelta
            d2 = d1 + relativedelta(months=1)
            duration = 1
            print(f"Warning {name}: Start date ({start}) >= End date ({end}). Forcing 1 month duration.")
            
        # Ensure UUID is valid format
        try:
            clean_id = str(uuid.UUID(p_id))
        except:
            clean_id = str(uuid.uuid4())
            
        data_to_insert.append((
            clean_id,
            name,
            d1.strftime('%Y-%m-%d'),
            d2.strftime('%Y-%m-%d'),
            float(budget),
            'USD',
            float(duration)
        ))


    if not data_to_insert:
        print("No valid data to migrate.")
        return

    print(f"Inserting {len(data_to_insert)} projects into Postgres... (Skipped {skipped_count} due to invalid dates or range)")

    
    # Use UPSERT logic (ON CONFLICT DO UPDATE) to avoid duplicates
    insert_query = """
        INSERT INTO projects (id, project_name, start_date, end_date, total_capital, currency, duration_months)
        VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            project_name = EXCLUDED.project_name,
            start_date = EXCLUDED.start_date,
            end_date = EXCLUDED.end_date,
            total_capital = EXCLUDED.total_capital,
            currency = EXCLUDED.currency,
            duration_months = EXCLUDED.duration_months,
            updated_at = NOW()
    """
    
    execute_values(pg_cur, insert_query, data_to_insert)
    pg_conn.commit()
    
    print("Migration complete!")
    
    pg_cur.close()
    pg_conn.close()
    sl_conn.close()

if __name__ == "__main__":
    migrate()
