import psycopg2
import os
import sys
from dotenv import load_dotenv

load_dotenv()
conn_str = os.getenv("DATABASE_URL")

def apply_schema():
    if not conn_str:
        print("Error: DATABASE_URL not found.")
        sys.exit(1)

    print("Applying database schema...")
    try:
        # Read the schema file
        with open('schema.sql', 'r') as f:
            schema_sql = f.read()

        # Connect and execute
        conn = psycopg2.connect(conn_str)
        conn.autocommit = True # Important for some commands like CREATE EXTENSION
        cur = conn.cursor()
        
        cur.execute(schema_sql)
        
        print("Schema applied successfully!")
        
        # Verify tables
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
        tables = cur.fetchall()
        print(f"Created tables: {[t[0] for t in tables]}")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error applying schema: {e}")
        sys.exit(1)

if __name__ == "__main__":
    apply_schema()
