from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import Optional
import sqlite3
import math

app = FastAPI(
    title="MoSPI APIx",
    docs_url="/swagger",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

def query_db(query: str, args: tuple = ()):
    with sqlite3.connect("airfare_index.db") as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(query, args).fetchall()]

def query_db_scalar(query: str, args: tuple = ()):
    with sqlite3.connect("airfare_index.db") as conn:
        cursor = conn.cursor()
        cursor.execute(query, args)
        row = cursor.fetchone()
        return row[0] if row else 0

DOCUMENTATION_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MoSPI APIx — Developer Documentation</title>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root { --primary: #2563eb; --bg-main: #f8fafc; --bg-card: #ffffff; --code-bg: #0f172a; --text-dark: #0f172a; --text-muted: #64748b; --border: #e2e8f0; --get-color: #059669; --get-bg: #ecfdf5; }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', -apple-system, sans-serif; background-color: var(--bg-main); color: var(--text-dark); line-height: 1.6; }
        header { background: #ffffff; border-bottom: 1px solid var(--border); padding: 18px 48px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 10; }
        .brand { display: flex; align-items: center; gap: 12px; font-weight: 700; font-size: 1.15rem; }
        .badge-version { background: #e0f2fe; color: #0369a1; font-size: 12px; padding: 2px 8px; border-radius: 999px; font-weight: 600; }
        .container { max-width: 1240px; margin: 0 auto; padding: 40px 24px; display: flex; flex-direction: column; gap: 24px; }
        .endpoint-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
        .endpoint-header { padding: 24px; border-bottom: 1px solid var(--border); }
        .method-badge { background: var(--get-bg); color: var(--get-color); font-weight: 700; font-size: 12px; padding: 4px 10px; border-radius: 6px; font-family: 'JetBrains Mono', monospace; }
        .endpoint-path { font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 1.05rem; }
        .endpoint-body { padding: 24px; }
        .code-block { background: var(--code-bg); color: #38bdf8; border-radius: 8px; padding: 16px 20px; font-family: 'JetBrains Mono', monospace; font-size: 13px; overflow-x: auto; }
    </style>
</head>
<body>
    <header>
        <div class="brand">✈️ MoSPI APIx <span class="badge-version">v1.2.0 (Paginated)</span></div>
    </header>
    <div class="container">
        <section class="endpoint-card">
            <div class="endpoint-header">
                <span class="method-badge">GET</span> <span class="endpoint-path">/api/fares/raw</span>
                <p style="color: #475569; margin-top: 8px;">Paginated raw extraction endpoint supporting <code>page</code>, <code>size</code>, <code>hours_back</code>, and exact <code>date</code> (YYYY-MM-DD).</p>
            </div>
            <div class="endpoint-body">
                <div class="code-block">curl "https://mospi-apix-api.onrender.com/api/fares/raw?page=1&size=50000&date=2026-09-17"</div>
            </div>
        </section>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
def get_documentation():
    return DOCUMENTATION_HTML

@app.get("/api/fares/raw")
def get_raw_fares(
    hours_back: int = Query(24, description="Lookback window in hours (ignored if date is passed)"),
    date: Optional[str] = Query(None, description="Specific scrape date in YYYY-MM-DD format"),
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    size: int = Query(50000, ge=1, le=50000, description="Records per page (max 50,000)")
):
    if date:
        count_query = "SELECT COUNT(*) FROM raw_fares WHERE date(timestamp) = ? AND total_fare IS NOT NULL"
        data_query_base = """
            SELECT id, timestamp, airline, flight_no as flight_number, route, 
                   advance_window_days, base_fare, taxes_fees, total_fare, 
                   ota_source, departure_time
            FROM raw_fares 
            WHERE date(timestamp) = ? AND total_fare IS NOT NULL
        """
        filter_params = (date,)
    else:
        time_modifier = f"-{hours_back} hours"
        count_query = """
            SELECT COUNT(*) FROM raw_fares 
            WHERE timestamp >= datetime('now', '+5 hours', '+30 minutes', ?) 
            AND total_fare IS NOT NULL
        """
        data_query_base = """
            SELECT id, timestamp, airline, flight_no as flight_number, route, 
                   advance_window_days, base_fare, taxes_fees, total_fare, 
                   ota_source, departure_time
            FROM raw_fares 
            WHERE timestamp >= datetime('now', '+5 hours', '+30 minutes', ?) 
            AND total_fare IS NOT NULL
        """
        filter_params = (time_modifier,)

    total_records = query_db_scalar(count_query, filter_params)
    total_pages = math.ceil(total_records / size) if total_records > 0 else 1

    offset = (page - 1) * size
    data_query = f"{data_query_base} ORDER BY id ASC LIMIT ? OFFSET ?"
    query_params = filter_params + (size, offset)

    results = query_db(data_query, query_params)

    return {
        "status": "ok",
        "pagination": {
            "total_records": total_records,
            "page": page,
            "size": size,
            "total_pages": total_pages,
            "has_next": page < total_pages
        },
        "records_count": len(results),
        "data": results
    }

@app.get("/api/fares/compare")
def compare_fares(
    route: str = Query(..., example="DEL-BOM"),
    window: int = Query(..., example=7)
):
    q = '''SELECT ota_source, airline, MIN(total_fare) as lowest_fare, ROUND(AVG(total_fare), 2) as average_fare
           FROM raw_fares 
           WHERE route = ? AND advance_window_days = ? 
           AND timestamp >= datetime('now', '+5 hours', '+30 minutes', '-24 hours')
           AND total_fare IS NOT NULL
           GROUP BY ota_source, airline 
           ORDER BY lowest_fare ASC'''
    return {
        "status": "ok",
        "route": route,
        "window": window,
        "comparisons": query_db(q, (route, window))
    }

@app.get("/api/fares/matrix")
def fare_matrix():
    q = '''SELECT route, advance_window_days as window, ROUND(AVG(total_fare), 2) as average_fare, COUNT(total_fare) as sample_count
           FROM raw_fares 
           WHERE timestamp >= datetime('now', '+5 hours', '+30 minutes', '-24 hours')
           AND total_fare IS NOT NULL
           GROUP BY route, advance_window_days 
           ORDER BY route ASC, window ASC'''
    return {
        "status": "ok",
        "matrix": query_db(q)
    }