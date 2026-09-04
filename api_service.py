from fastapi import FastAPI
import sqlite3
import pandas as pd

app = FastAPI(title="MoSPI APIx REST Service", version="1.0")

def get_db_connection():
    conn = sqlite3.connect('airfare_index.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/v1/apix/latest")
def get_latest_index():
    """Returns the most recent calculated APIx value in MoSPI JSON format."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM daily_index ORDER BY date DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {"status": "success", "data": dict(row)}
    return {"status": "error", "message": "No index calculated yet"}

@app.get("/api/v1/fares/raw")
def get_raw_fares(route: str = "DEL-BOM", window: int = 7):
    """Allows MoSPI servers to query specific routes and windows dynamically."""
    conn = get_db_connection()
    df = pd.read_sql_query(
        "SELECT * FROM raw_fares WHERE route = ? AND advance_window_days = ?", 
        conn, params=(route, window)
    )
    conn.close()
    return {"status": "success", "record_count": len(df), "data": df.to_dict(orient="records")}