from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import sqlite3

tags_metadata = [
    {
        "name": "Airfare Comparisons",
        "description": "Cross-portal rate comparisons between airline direct websites and OTAs.",
    },
    {
        "name": "APIx Index & Matrices",
        "description": "Aggregated price distributions and multi-sector rate indices for MoSPI reporting.",
    },
]

app = FastAPI(
    title="MoSPI APIx — Airfare Price Index API",
    description="""
## Real-Time Airfare Monitoring & Price Index Service

The **MoSPI APIx** API allows researchers, economists, and analysts to programmaticly access real-time domestic airfare data tracked across **20 primary domestic sectors** and **5 advance purchase windows (T+1 to T+45)**.

### Portals Monitored:
* **Direct Airlines:** Akasa Air, SpiceJet
* **Online Travel Agencies (OTAs):** Yatra, EaseMyTrip

---
*Run queries against `/docs` for interactive testing or inspect endpoints below.*
    """,
    version="1.0.0",
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
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

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def root_documentation():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MoSPI APIx — Reference & Quickstart</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #222; }
            pre { background: #f4f4f5; padding: 14px; border-radius: 6px; overflow-x: auto; font-size: 14px; }
            code { background: #f4f4f5; padding: 2px 6px; border-radius: 4px; font-size: 13px; }
            .endpoint { border-left: 4px solid #0284c7; padding-left: 14px; margin: 24px 0; }
            .badge { display: inline-block; background: #0284c7; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }
            a { color: #0284c7; text-decoration: none; font-weight: 500; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <h1>✈️ MoSPI APIx — API Documentation & Quickstart</h1>
        <p>Welcome to the <strong>Airfare Price Index (APIx)</strong> microservice. Access structured domestic airfare records, cross-portal price deviations, and index metrics.</p>
        
        <p>👉 <strong>Interactive Swagger UI:</strong> <a href="/docs">Open /docs</a> | <strong>ReDoc:</strong> <a href="/redoc">Open /redoc</a></p>
        
        <h2>Available Endpoints</h2>
        
        <div class="endpoint">
            <p><span class="badge">GET</span> <code>/api/fares/compare</code></p>
            <p>Compares portal fares (Direct vs. OTAs) for a specific route and advance window over the last 24 hours.</p>
            <h4>Query Parameters:</h4>
            <ul>
                <li><code>route</code> (e.g., <code>DEL-BOM</code>) — IATA origin and destination pair.</li>
                <li><code>window</code> (e.g., <code>7</code>) — Advance purchase window in days (1, 7, 15, 30, 45).</li>
            </ul>
            <h4>Example Request:</h4>
            <pre>GET /api/fares/compare?route=DEL-BOM&window=7</pre>
            <h4>Sample Response:</h4>
            <pre>{
  "status": "ok",
  "route": "DEL-BOM",
  "window": 7,
  "comparisons": [
    {
      "ota_source": "Akasa Direct",
      "airline": "Akasa Air",
      "lowest_fare": 4530.0,
      "average_fare": 4890.5
    },
    {
      "ota_source": "Yatra",
      "airline": "SpiceJet",
      "lowest_fare": 4720.0,
      "average_fare": 5100.0
    }
  ]
}</pre>
        </div>

        <div class="endpoint">
            <p><span class="badge">GET</span> <code>/api/fares/matrix</code></p>
            <p>Generates the average fare across all routes and advance windows observed in the past 24 hours.</p>
            <h4>Example Request:</h4>
            <pre>GET /api/fares/matrix</pre>
        </div>
    </body>
    </html>
    """

@app.get(
    "/api/fares/compare",
    tags=["Airfare Comparisons"],
    summary="Compare portal fares across a sector",
    response_description="Array of portal and airline fare aggregations."
)
def compare_fares(
    route: str = Query(..., example="DEL-BOM", description="Sector pair formatted as ORIGIN-DESTINATION (IATA)"),
    window: int = Query(..., example=7, description="Advance booking window (1, 7, 15, 30, 45)")
):
    """
    Retrieve lowest and mean fares broken down by `ota_source` and `airline` for a route and purchase window.
    
    * Only returns records captured within the last **24 hours**.
    * Useful for verifying cross-portal pricing anomalies (Direct Airline Portal vs. Aggregators).
    """
    q = '''SELECT ota_source, airline, MIN(total_fare) as lowest_fare, ROUND(AVG(total_fare), 2) as average_fare
           FROM raw_fares WHERE route = ? AND advance_window_days = ? AND timestamp >= datetime('now', '-24 hours')
           GROUP BY ota_source, airline ORDER BY lowest_fare ASC'''
    return {
        "status": "ok",
        "route": route,
        "window": window,
        "comparisons": query_db(q, (route, window))
    }

@app.get(
    "/api/fares/matrix",
    tags=["APIx Index & Matrices"],
    summary="Fetch all-sector fare aggregation matrix",
    response_description="Averaged ticket price per route per advance window."
)
def fare_matrix():
    """
    Build a cross-sector matrix of aggregated average ticket prices across all 5 advance booking windows.
    """
    q = '''SELECT route, advance_window_days as window, ROUND(AVG(total_fare), 2) as average_fare, COUNT(*) as sample_count
           FROM raw_fares WHERE timestamp >= datetime('now', '-24 hours')
           GROUP BY route, advance_window_days ORDER BY route ASC, window ASC'''
    return {
        "status": "ok",
        "matrix": query_db(q)
    }