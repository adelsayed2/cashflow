import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

db_url = os.getenv("DATABASE_URL")

cols = [
    "developer", "main_contractor", "lead_consultant", "architect", 
    "pmc", "cost_consultant", "structural_engineer", 
    "mep_contractor", "landscape_architect"
]

def find_best_project():
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # Count non-null and non-empty stakeholder fields
        score_calc = " + ".join([f"(CASE WHEN {c} IS NOT NULL AND {c} != '' THEN 1 ELSE 0 END)" for c in cols])
        
        query = f"""
            SELECT id, project_name, {score_calc} as score
            FROM projects
            ORDER BY score DESC, created_at DESC
            LIMIT 5
        """
        
        cur.execute(query)
        rows = cur.fetchall()
        
        for row in rows:
            print(f"ID: {row[0]} | Name: {row[1]} | Data Score: {row[2]}/{len(cols)}")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_best_project()
