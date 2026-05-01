import psycopg2
import sys
import os
from dotenv import load_dotenv

load_dotenv()
conn_str = os.getenv("DATABASE_URL")

def test_connection():
    if not conn_str:
        print("Error: DATABASE_URL not found in environment.")
        sys.exit(1)
        
    print(f"Connecting to database using .env...")
    try:
        conn = psycopg2.connect(conn_str)
        cur = conn.cursor()
        cur.execute("SELECT version();")
        db_version = cur.fetchone()
        print(f"Success! Database version: {db_version[0]}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_connection()
