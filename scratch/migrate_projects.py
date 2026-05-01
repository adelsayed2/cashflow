import sqlite3
import psycopg2
import os
import sys
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

load_dotenv()
PG_CONN_STR = os.getenv("DATABASE_URL")
SL_DB_PATH = "/Users/adelsayed/Documents/code/project-agent/data/agci.db"

def migrate():
    if not PG_CONN_STR:
        print("Error: DATABASE_URL not found.")
        sys.exit(1)

    print("Starting migration from SQLite to PostgreSQL...")
    try:
        # Connect to databases
        sl_conn = sqlite3.connect(SL_DB_PATH)
        sl_cur = sl_conn.cursor()
        
        pg_conn = psycopg2.connect(PG_CONN_STR)
        pg_cur = pg_conn.cursor()

        # Fetch projects with necessary data
        # Mapping: name, start_date, completion_date, budget_value_local, budget_currency
        sl_cur.execute("""
            SELECT name, start_date, completion_date, budget_value_local, budget_currency 
            FROM projects 
            WHERE name IS NOT NULL 
              AND start_date IS NOT NULL 
              AND completion_date IS NOT NULL 
              AND budget_value_local > 0
        """)
        
        projects = sl_cur.fetchall()
        print(f"Found {len(projects)} projects to migrate.")

        inserted_count = 0
        for p in projects:
            name, start, end, budget, currency = p
            
            try:
                # Calculate duration in months
                d1 = datetime.strptime(start, '%Y-%m-%d')
                d2 = datetime.strptime(end, '%Y-%m-%d')
                delta = relativedelta(d2, d1)
                duration = delta.years * 12 + delta.months + (delta.days / 30.0)
                
                if duration <= 0:
                    continue

                # Insert into PostgreSQL
                pg_cur.execute("""
                    INSERT INTO projects (project_name, start_date, end_date, total_capital, currency, duration_months)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                """, (name, start, end, budget, currency or 'USD', duration))
                
                inserted_count += 1
            except Exception as e:
                print(f"Skipping project '{name}': {e}")

        pg_conn.commit()
        print(f"Successfully migrated {inserted_count} projects.")

        sl_conn.close()
        pg_conn.close()
    except Exception as e:
        print(f"Migration error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate()
