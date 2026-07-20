import os
import json
import sqlite3
import time
from pathlib import Path

def seed():
    db_path = Path("/app/backend/data/webui.db")
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return
        
    pipe_path = Path("/app/backend/data/functions/data_pipe.py")
    if not pipe_path.exists():
        print(f"data_pipe.py not found at {pipe_path}")
        return
        
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # 1. Fetch first admin user
    cursor.execute("SELECT id FROM user WHERE role = 'admin' ORDER BY created_at ASC LIMIT 1")
    row = cursor.fetchone()
    user_id = row[0] if row else None
    if not user_id:
        # Fallback to any user
        cursor.execute("SELECT id FROM user ORDER BY created_at ASC LIMIT 1")
        row = cursor.fetchone()
        user_id = row[0] if row else "admin"
        
    print(f"Registering function under user_id: {user_id}")
    
    # 2. Read pipe content
    with open(pipe_path, "r") as f:
        content = f.read()
        
    # 3. Define metadata & valves
    meta = {
        "description": "Fink Finance Due Diligence Agent",
        "manifest": {}
    }
    
    valves = {
        "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
        "ALPHAVANTAGE_API_KEY": os.environ.get("ALPHAVANTAGE_API_KEY", ""),
        "GEMINI_MODEL": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    }
    
    now = int(time.time())
    
    # 4. Insert or Replace row
    cursor.execute("""
        INSERT OR REPLACE INTO function (
            id, user_id, name, type, content, meta, valves, is_active, is_global, updated_at, created_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, (
        "data_pipe",
        user_id,
        "Fink Finance Due Diligence Agent",
        "pipe",
        content,
        json.dumps(meta),
        json.dumps(valves),
        1, # is_active
        1, # is_global
        now,
        now
    ))
    
    conn.commit()
    conn.close()
    print("Successfully registered 'Fink Finance Due Diligence Agent' in Open WebUI database!")

if __name__ == "__main__":
    seed()
