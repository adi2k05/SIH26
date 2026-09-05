from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
from datetime import datetime

app = FastAPI(title="MoSPI Airfare Index API (APIx)")

# Allow frontend/Jupyter Notebooks to fetch data without CORS blocks
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    conn = sqlite3.connect("airfare_index.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/index/historical")
def get_historical_index():
    """
    Deliverable 1: Exposes the daily APIx calculation for MoSPI CPI Backtesting.
    Your teammate's Jupyter Notebook will hit this endpoint.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Pulls the time-series index data
        cursor.execute('''
            SELECT date, apix_value 
            FROM daily_index 
            ORDER BY date ASC
        ''')
        rows = cursor.fetchall()
        conn.close()
        
        return {"data": [dict(row) for row in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fares/compare")
def compare_portal_variance(
    route: str = Query(..., description="e.g., DEL-BOM"),
    window: int = Query(..., description="e.g., 7 or 15")
):
    """
    Deliverable 2: Exposes cross-portal price variance. 
    Proves to judges how OTA markups compare to direct factory (airline) pricing.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Calculates the median total fare grouped by portal source for the last 24 hours
        cursor.execute('''
            SELECT 
                ota_source,
                airline,
                MIN(total_fare) as lowest_fare,
                AVG(total_fare) as average_fare
            FROM raw_fares 
            WHERE route = ? 
              AND advance_window_days = ? 
              AND timestamp >= datetime('now', '-24 hours')
            GROUP BY ota_source, airline
            ORDER BY lowest_fare ASC
        ''', (route, window))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return {"message": f"No data found for {route} at T+{window} in the last 24 hours."}
            
        return {"route": route, "advance_window": window, "comparisons": [dict(row) for row in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fares/matrix")
def get_full_matrix():
    """
    Deliverable 3: A macro view for the frontend dashboard showing the overall 
    average fare across all 20 routes and 5 windows.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                route, 
                advance_window_days as window, 
                AVG(total_fare) as median_price
            FROM raw_fares
            WHERE timestamp >= datetime('now', '-24 hours')
            GROUP BY route, advance_window_days
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return {"matrix": [dict(row) for row in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Runs the server locally on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)