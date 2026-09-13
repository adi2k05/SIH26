from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import sqlite3

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

DOCUMENTATION_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MoSPI APIx — Developer Documentation</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --bg-main: #f8fafc;
            --bg-card: #ffffff;
            --code-bg: #0f172a;
            --text-dark: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --get-color: #059669;
            --get-bg: #ecfdf5;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: var(--bg-main);
            color: var(--text-dark);
            line-height: 1.6;
        }
        header {
            background: #ffffff;
            border-bottom: 1px solid var(--border);
            padding: 18px 48px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
            font-weight: 700;
            font-size: 1.15rem;
            color: #0f172a;
        }
        .badge-version {
            background: #e0f2fe;
            color: #0369a1;
            font-size: 12px;
            padding: 2px 8px;
            border-radius: 999px;
            font-weight: 600;
        }
        .nav-links a {
            color: var(--text-muted);
            text-decoration: none;
            font-size: 14px;
            font-weight: 500;
            margin-left: 20px;
        }
        .nav-links a:hover { color: var(--primary); }
        .container {
            max-width: 1240px;
            margin: 0 auto;
            padding: 40px 24px 80px;
            display: grid;
            grid-template-columns: 240px 1fr;
            gap: 48px;
        }
        .sidebar {
            position: sticky;
            top: 90px;
            height: fit-content;
        }
        .sidebar h4 {
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: var(--text-muted);
            margin-bottom: 12px;
        }
        .sidebar ul { list-style: none; }
        .sidebar li { margin-bottom: 8px; }
        .sidebar a {
            display: block;
            color: #334155;
            text-decoration: none;
            font-size: 14px;
            padding: 6px 10px;
            border-radius: 6px;
            transition: all 0.15s;
        }
        .sidebar a:hover {
            background: #e2e8f0;
            color: #0f172a;
        }
        .content { display: flex; flex-direction: column; gap: 48px; }
        .intro h1 { font-size: 2rem; font-weight: 800; margin-bottom: 12px; }
        .intro p { color: #475569; font-size: 1.05rem; }
        .meta-box {
            margin-top: 16px;
            padding: 16px 20px;
            background: #ffffff;
            border: 1px solid var(--border);
            border-radius: 8px;
            display: flex;
            gap: 32px;
        }
        .meta-item small { display: block; font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 600; }
        .meta-item span { font-weight: 600; font-size: 14px; }
        .endpoint-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.03);
            overflow: hidden;
        }
        .endpoint-header {
            padding: 24px;
            border-bottom: 1px solid var(--border);
        }
        .endpoint-title {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
        }
        .method-badge {
            background: var(--get-bg);
            color: var(--get-color);
            font-weight: 700;
            font-size: 12px;
            padding: 4px 10px;
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
        }
        .endpoint-path {
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
            font-size: 1.05rem;
            color: #0f172a;
        }
        .endpoint-desc { color: #475569; font-size: 14px; }
        .endpoint-body {
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 24px;
        }
        h3 { font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 10px; }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13.5px;
            text-align: left;
        }
        th {
            background: #f1f5f9;
            padding: 10px 14px;
            font-weight: 600;
            color: #334155;
            border-bottom: 1px solid var(--border);
        }
        td {
            padding: 12px 14px;
            border-bottom: 1px solid var(--border);
            vertical-align: top;
        }
        .param-name { font-family: 'JetBrains Mono', monospace; font-weight: 600; color: #0369a1; }
        .param-type { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #64748b; }
        .param-req { font-size: 11px; font-weight: 700; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; }
        .req-true { background: #fee2e2; color: #b91c1c; }
        .req-false { background: #f1f5f9; color: #475569; }
        .response-container {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .code-block {
            background: var(--code-bg);
            color: #f8fafc;
            border-radius: 8px;
            padding: 16px 20px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            overflow-x: auto;
            line-height: 1.5;
        }
        .code-block code { color: #38bdf8; }
        .code-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            color: var(--text-muted);
            margin-bottom: 4px;
        }
    </style>
</head>
<body>
    <header>
        <div class="brand">
            ✈️ MoSPI APIx
            <span class="badge-version">v1.1.0</span>
        </div>
        <div class="nav-links">
            <a href="#quickstart">Quickstart</a>
            <a href="#endpoint-raw">/raw (ML)</a>
            <a href="#endpoint-compare">/compare</a>
            <a href="#endpoint-matrix">/matrix</a>
        </div>
    </header>

    <div class="container">
        <aside class="sidebar">
            <h4>Getting Started</h4>
            <ul>
                <li><a href="#quickstart">Integration Guide</a></li>
            </ul>
            <h4 style="margin-top: 24px;">Endpoints</h4>
            <ul>
                <li><a href="#endpoint-raw">GET /api/fares/raw</a></li>
                <li><a href="#endpoint-compare">GET /api/fares/compare</a></li>
                <li><a href="#endpoint-matrix">GET /api/fares/matrix</a></li>
            </ul>
            <h4 style="margin-top: 24px;">Resources</h4>
            <ul>
                <li><a href="/swagger">Interactive Console</a></li>
            </ul>
        </aside>

        <main class="content">
            <section class="intro">
                <h1>API Reference</h1>
                <p>Welcome to the <strong>Airfare Price Index (APIx)</strong> programmatic interface. All endpoints return JSON payloads filtered for clean analytical and machine learning integration.</p>
                <div class="meta-box">
                    <div class="meta-item">
                        <small>Data Sources</small>
                        <span>Akasa, SpiceJet, Yatra, EMT</span>
                    </div>
                    <div class="meta-item">
                        <small>Coverage</small>
                        <span>20 Sectors &bull; T+1 to T+45 Days</span>
                    </div>
                    <div class="meta-item">
                        <small>Active Base URL</small>
                        <code>https://mospi-apix-api.onrender.com</code>
                    </div>
                </div>
            </section>

            <!-- QUICKSTART SECTION -->
            <section id="quickstart" class="endpoint-card">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="endpoint-path">🚀 How to Use This API</span>
                    </div>
                    <p class="endpoint-desc">Integrate APIx data directly into your machine learning pipelines, backend services, or terminal using standard HTTP requests.</p>
                </div>
                <div class="endpoint-body">
                    <div>
                        <h3>Python (For ML & Data Science)</h3>
                        <p style="font-size: 14px; color: #475569; margin-bottom: 12px;">Fetch the raw dataset and load it directly into a Pandas DataFrame for training.</p>
                        <div class="code-block">
<pre>import requests
import pandas as pd

# 1. Fetch data from the live API
url = "https://mospi-apix-api.onrender.com/api/fares/raw?hours_back=24"
response = requests.get(url).json()

# 2. Parse into DataFrame
if response.get("status") == "ok":
    df = pd.DataFrame(response["data"])
    print(f"Loaded {len(df)} records!")
    print(df.head())
else:
    print("Error fetching data.")</pre>
                        </div>
                    </div>
                    
                    <div style="margin-top: 16px;">
                        <h3>cURL (For Terminal Testing)</h3>
                        <div class="code-block">
<pre>curl -X GET "https://mospi-apix-api.onrender.com/api/fares/compare?route=DEL-BOM&window=7" \
     -H "Accept: application/json"</pre>
                        </div>
                    </div>
                </div>
            </section>

            <!-- 1. RAW ENDPOINT FOR ML -->
            <section id="endpoint-raw" class="endpoint-card">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method-badge">GET</span>
                        <span class="endpoint-path">/api/fares/raw</span>
                    </div>
                    <p class="endpoint-desc">Retrieves flat, unaggregated ticket price records. Null and non-operated records are stripped out automatically for direct ML consumption.</p>
                </div>
                <div class="endpoint-body">
                    <div>
                        <h3>Request Parameters</h3>
                        <table>
                            <thead>
                                <tr><th>Parameter</th><th>Type</th><th>Required</th><th>Description</th></tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td class="param-name">hours_back</td>
                                    <td class="param-type">integer</td>
                                    <td><span class="param-req req-false">Optional</span></td>
                                    <td>Lookback window in hours. Default: <code>24</code>.</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    <div class="response-container">
                        <div class="code-header"><span>Sample JSON Response</span></div>
                        <div class="code-block">
<pre>{
  "status": "ok",
  "records_count": 2,
  "data": [
    {
      "timestamp": "2026-09-07 14:10:02",
      "airline": "Air India",
      "route": "DEL-BOM",
      "advance_window_days": 7,
      "base_fare": 4650.0,
      "taxes_fees": 820.5,
      "total_fare": 5470.5,
      "ota_source": "EaseMyTrip"
    }
  ]
}</pre>
                        </div>
                    </div>
                </div>
            </section>

            <!-- 2. COMPARE ENDPOINT -->
            <section id="endpoint-compare" class="endpoint-card">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method-badge">GET</span>
                        <span class="endpoint-path">/api/fares/compare</span>
                    </div>
                    <p class="endpoint-desc">Compares channel-specific pricing (Direct Airlines vs. OTAs) for a specific route and booking window over the past 24 hours.</p>
                </div>
                <div class="endpoint-body">
                    <div>
                        <h3>Request Parameters</h3>
                        <table>
                            <thead>
                                <tr><th>Parameter</th><th>Type</th><th>Required</th><th>Description</th></tr>
                            </thead>
                            <tbody>
                                <tr>
                                    <td class="param-name">route</td>
                                    <td class="param-type">string</td>
                                    <td><span class="param-req req-true">Required</span></td>
                                    <td>Origin and destination pair in IATA format (e.g., <code>DEL-BOM</code>).</td>
                                </tr>
                                <tr>
                                    <td class="param-name">window</td>
                                    <td class="param-type">integer</td>
                                    <td><span class="param-req req-true">Required</span></td>
                                    <td>Advance purchase window in days (<code>1</code>, <code>7</code>, <code>15</code>, <code>30</code>, <code>45</code>).</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    <div class="response-container">
                        <div class="code-header"><span>Sample JSON Response</span></div>
                        <div class="code-block">
<pre>{
  "status": "ok",
  "route": "DEL-BOM",
  "window": 7,
  "comparisons": [
    {
      "ota_source": "Akasa Direct",
      "airline": "Akasa Air",
      "lowest_fare": 4847.0,
      "average_fare": 5120.0
    }
  ]
}</pre>
                        </div>
                    </div>
                </div>
            </section>

            <!-- 3. MATRIX ENDPOINT -->
            <section id="endpoint-matrix" class="endpoint-card">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method-badge">GET</span>
                        <span class="endpoint-path">/api/fares/matrix</span>
                    </div>
                    <p class="endpoint-desc">Returns a consolidated macro matrix calculating the 24-hour mean fare across every tracked sector and advance window.</p>
                </div>
                <div class="endpoint-body">
                    <div class="response-container">
                        <div class="code-header"><span>Sample JSON Response</span></div>
                        <div class="code-block">
<pre>{
  "status": "ok",
  "matrix": [
    {
      "route": "DEL-BOM",
      "window": 1,
      "average_fare": 7450.0,
      "sample_count": 82
    }
  ]
}</pre>
                        </div>
                    </div>
                </div>
            </section>
        </main>
    </div>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
def get_documentation():
    return DOCUMENTATION_HTML

@app.get("/api/fares/raw")
def get_raw_fares(hours_back: int = Query(24, description="Lookback hours")):
    q = '''SELECT timestamp, airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source
           FROM raw_fares 
           WHERE timestamp >= datetime('now', ?) 
           AND total_fare IS NOT NULL
           ORDER BY timestamp DESC'''
    time_modifier = f"-{hours_back} hours"
    results = query_db(q, (time_modifier,))
    return {
        "status": "ok",
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
           AND timestamp >= datetime('now', '-24 hours')
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
           WHERE timestamp >= datetime('now', '-24 hours')
           AND total_fare IS NOT NULL
           GROUP BY route, advance_window_days 
           ORDER BY route ASC, window ASC'''
    return {
        "status": "ok",
        "matrix": query_db(q)
    }
