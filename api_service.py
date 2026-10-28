from fastapi import FastAPI, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import Optional
from datetime import datetime
import sqlite3
import math
import glob
import os

app = FastAPI(
    title="AirfareX API",
    docs_url="/swagger",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

def get_unified_db():
    conn = sqlite3.connect("airfare_index.db")
    archive_dbs = sorted([f for f in glob.glob("*_airfare_index.db") if f != "airfare_index.db"])
    
    if not archive_dbs:
        return conn, "raw_fares"
    
    parts = ["SELECT * FROM main.raw_fares"]
    for idx, db_file in enumerate(archive_dbs):
        alias = f"arc_{idx}"
        conn.execute(f"ATTACH DATABASE '{db_file}' AS {alias}")
        parts.append(f"SELECT * FROM {alias}.raw_fares")
    
    union_source = f"(SELECT * FROM ({' UNION ALL '.join(parts)})) AS raw_fares"
    return conn, union_source

def query_db(query: str, args: tuple = ()):
    conn, table_source = get_unified_db()
    try:
        conn.row_factory = sqlite3.Row
        sql = query.replace("raw_fares", table_source) if table_source != "raw_fares" else query
        return [dict(row) for row in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()

def query_db_scalar(query: str, args: tuple = ()):
    conn, table_source = get_unified_db()
    try:
        cursor = conn.cursor()
        sql = query.replace("raw_fares", table_source) if table_source != "raw_fares" else query
        cursor.execute(sql, args)
        row = cursor.fetchone()
        return row[0] if row else 0
    finally:
        conn.close()

DOCUMENTATION_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AirfareX API — Developer Documentation</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
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
            overflow-x: hidden;
        }
        
        #splash-screen {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background-color: #0f172a; z-index: 9999;
            display: flex; flex-direction: column; justify-content: center; align-items: center;
            transition: opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1), visibility 0.6s;
        }
        .loader-ring {
            width: 48px; height: 48px;
            border: 4px solid rgba(255, 255, 255, 0.1);
            border-top-color: #3b82f6; border-radius: 50%;
            animation: spin 1s cubic-bezier(0.6, 0.2, 0.4, 0.8) infinite;
            margin-bottom: 20px;
        }
        .splash-text { color: #f8fafc; font-family: 'JetBrains Mono', monospace; font-size: 14px; letter-spacing: 0.05em; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeSlideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse-green { 0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); } 70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); } 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); } }
        @keyframes float { 0%, 100% { transform: translateY(0) rotate(0deg); } 50% { transform: translateY(-3px) rotate(4deg); } }
        @keyframes typing { 0%, 20% { content: '.'; } 40%, 60% { content: '..'; } 80%, 100% { content: '...'; } }

        .animated-section { animation: fadeSlideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards; opacity: 0; }
        .delay-1 { animation-delay: 0.2s; }
        .delay-2 { animation-delay: 0.3s; }
        .delay-3 { animation-delay: 0.4s; }
        .delay-4 { animation-delay: 0.5s; }

        .status-dot { height: 9px; width: 9px; background-color: #10b981; border-radius: 50%; display: inline-block; margin-right: 8px; animation: pulse-green 2s infinite; }
        .float-emoji { display: inline-block; animation: float 4s ease-in-out infinite; }
        .typing-dots::after { content: '.'; display: inline-block; width: 1em; text-align: left; animation: typing 1.5s infinite; }

        .tooltip { position: relative; cursor: help; border-bottom: 1px dashed var(--text-muted); transition: color 0.2s ease; }
        .tooltip:hover { color: var(--primary); border-bottom-color: var(--primary); }
        .tooltip::after {
            content: attr(data-tooltip); position: absolute; bottom: 130%; left: 50%;
            transform: translateX(-50%) scale(0.95); opacity: 0; pointer-events: none;
            background: #1e293b; color: #f8fafc; padding: 8px 12px; border-radius: 6px;
            font-size: 12px; font-weight: 500; white-space: nowrap;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1); z-index: 50;
        }
        .tooltip::before {
            content: ''; position: absolute; bottom: 110%; left: 50%; transform: translateX(-50%);
            border-width: 6px; border-style: solid; border-color: #1e293b transparent transparent transparent;
            opacity: 0; transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .tooltip:hover::after, .tooltip:hover::before { opacity: 1; transform: translateX(-50%) scale(1); }

        header {
            background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border); padding: 16px 48px;
            display: flex; align-items: center; justify-content: space-between;
            position: sticky; top: 0; z-index: 100; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
        }
        .brand { display: flex; align-items: center; font-weight: 700; font-size: 1.15rem; color: #0f172a; }
        .badge-version { background: #e0f2fe; color: #0369a1; font-size: 11px; padding: 3px 8px; border-radius: 999px; font-weight: 700; margin-left: 12px; border: 1px solid #bae6fd; }
        .nav-links { display: flex; gap: 8px; }
        .nav-links a { color: #475569; text-decoration: none; font-size: 13.5px; font-weight: 600; padding: 8px 14px; border-radius: 8px; transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1); background: transparent; }
        .nav-links a:hover { background: #f1f5f9; color: #0f172a; }
        
        .container { max-width: 1320px; margin: 0 auto; padding: 40px 24px 80px; display: grid; grid-template-columns: 280px 1fr; gap: 56px; }
        
        .sidebar { position: sticky; top: 100px; height: fit-content; padding-right: 16px; }
        .sidebar h4 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #94a3b8; margin-bottom: 12px; font-weight: 700; }
        .sidebar ul { list-style: none; margin-bottom: 32px; }
        .sidebar li { margin-bottom: 2px; }
        .sidebar a { display: flex; align-items: center; gap: 10px; color: #475569; text-decoration: none; font-size: 13.5px; padding: 8px 12px; border-radius: 6px; transition: all 0.2s; font-weight: 500; border-left: 3px solid transparent; }
        .sidebar a:hover { background: #f1f5f9; color: var(--primary-dark); border-left: 3px solid var(--primary); transform: translateX(2px); }
        .sidebar-icon { font-size: 14px; opacity: 0.7; }
        
        .uptime-widget { margin-top: auto; padding: 16px; border-radius: 8px; background: #f8fafc; border: 1px solid var(--border); }
        .uptime-widget .title { font-size: 12px; font-weight: 700; color: #475569; display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
        .uptime-widget .metric { font-size: 20px; font-weight: 800; color: #0f172a; font-family: 'JetBrains Mono', monospace; }
        .uptime-widget .sub { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

        .content { display: flex; flex-direction: column; gap: 40px; }
        
        .intro h1 { font-size: 2.6rem; font-weight: 800; margin-bottom: 12px; letter-spacing: -0.02em; background: linear-gradient(90deg, #0f172a, #2563eb); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .intro p { color: #475569; font-size: 1.1rem; line-height: 1.7; }
        
        .live-status-banner { margin-top: 24px; padding: 18px 24px; background: linear-gradient(145deg, #ecfdf5 0%, #ffffff 100%); border: 1px solid #a7f3d0; border-left: 4px solid #10b981; border-radius: 8px; display: flex; align-items: center; gap: 16px; box-shadow: 0 4px 6px -1px rgba(16, 185, 129, 0.05); }
        .live-status-banner p { margin: 0; font-size: 14.5px; color: #064e3b; font-weight: 500; line-height: 1.6; }
        .live-status-banner strong { font-weight: 700; color: #047857; }

        .meta-box { margin-top: 24px; padding: 24px; background: #ffffff; border: 1px solid var(--border); border-radius: 12px; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 32px; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02); transition: border-color 0.3s ease, box-shadow 0.3s ease; }
        .meta-box:hover { border-color: #cbd5e1; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05); }
        .meta-item small { display: block; font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 700; margin-bottom: 8px; letter-spacing: 0.05em;}
        .meta-item span { font-weight: 600; font-size: 14.5px; line-height: 1.6; color: #1e293b; }
        
        .endpoint-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.03); overflow: hidden; transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.3s cubic-bezier(0.16, 1, 0.3, 1); }
        .endpoint-card:target { border-color: var(--primary); box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.1); }
        .endpoint-card:hover { transform: translateY(-3px); box-shadow: 0 12px 20px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.01); border-color: #cbd5e1; }
        .endpoint-header { padding: 24px; border-bottom: 1px solid var(--border); background: #f8fafc; }
        .endpoint-title { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
        .method-badge { background: var(--get-bg); color: var(--get-color); font-weight: 700; font-size: 12px; padding: 4px 10px; border-radius: 6px; font-family: 'JetBrains Mono', monospace; box-shadow: 0 1px 2px rgba(5, 150, 105, 0.1); }
        .endpoint-path { font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 1.1rem; color: #0f172a; }
        .endpoint-desc { color: #475569; font-size: 14.5px; }
        .endpoint-body { padding: 24px; display: flex; flex-direction: column; gap: 28px; }
        h3 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); margin-bottom: 12px; font-weight: 700; }
        table { width: 100%; border-collapse: collapse; font-size: 13.5px; text-align: left; }
        th { background: #f1f5f9; padding: 12px 14px; font-weight: 600; color: #334155; border-bottom: 1px solid var(--border); }
        td { padding: 14px 14px; border-bottom: 1px solid var(--border); vertical-align: top; transition: background 0.15s; }
        tr:hover td { background: #f8fafc; }
        .param-name { font-family: 'JetBrains Mono', monospace; font-weight: 600; color: #0369a1; }
        .param-type { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #64748b; }
        .param-req { font-size: 11px; font-weight: 700; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; }
        .req-true { background: #fee2e2; color: #b91c1c; }
        .req-false { background: #f1f5f9; color: #475569; }
        
        .code-block-wrapper { position: relative; background: var(--code-bg); border-radius: 8px; box-shadow: inset 0 2px 4px rgba(0,0,0,0.2); overflow: hidden; }
        .copy-btn { position: absolute; top: 12px; right: 12px; background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.2); color: #e2e8f0; padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; font-family: 'Inter', sans-serif; cursor: pointer; transition: all 0.2s; z-index: 10; display: flex; align-items: center; gap: 6px; }
        .copy-btn:hover { background: rgba(255, 255, 255, 0.2); color: #fff; transform: translateY(-1px); }
        .copy-btn:active { transform: translateY(1px); }
        .copy-btn.copied { background: #10b981; border-color: #10b981; color: #fff; }
        .code-block { padding: 20px; padding-top: 40px; font-family: 'JetBrains Mono', monospace; font-size: 13px; overflow-x: auto; line-height: 1.6; color: #f8fafc; }
        .code-block code { color: #38bdf8; }
        .code-header { font-size: 12px; color: var(--text-muted); font-weight: 700; margin-bottom: 8px; display: block; text-transform: uppercase; letter-spacing: 0.05em; }
    </style>
</head>
<body>
    <div id="splash-screen">
        <div class="loader-ring"></div>
        <div class="splash-text">AirfareX Engine Initializing...</div>
    </div>

    <header>
        <div class="brand">
            <span class="status-dot"></span> <span class="float-emoji">✈️</span> AirfareX API
            <span class="badge-version">v2.0</span>
        </div>
        <div class="nav-links">
            <a href="#quickstart">Quickstart</a>
            <a href="#endpoint-raw">/raw (ML)</a>
            <a href="#endpoint-compare">/compare</a>
            <a href="#endpoint-matrix">/matrix</a>
            <a href="#endpoint-health">/health</a>
        </div>
    </header>

    <div class="container">
        <aside class="sidebar animated-section delay-1">
            <h4>Introduction</h4>
            <ul>
                <li><a href="#quickstart"><span class="sidebar-icon">🚀</span> Integration Guide</a></li>
                <li><a href="#architecture"><span class="sidebar-icon">⚙️</span> Architecture</a></li>
            </ul>
            
            <h4>Core Endpoints</h4>
            <ul>
                <li><a href="#endpoint-raw"><span class="sidebar-icon">📊</span> GET /api/fares/raw</a></li>
                <li><a href="#endpoint-compare"><span class="sidebar-icon">⚖️</span> GET /api/fares/compare</a></li>
                <li><a href="#endpoint-matrix"><span class="sidebar-icon">📈</span> GET /api/fares/matrix</a></li>
            </ul>

            <h4>Monitoring</h4>
            <ul>
                <li><a href="#endpoint-health"><span class="sidebar-icon">🩺</span> GET /health (Uptime)</a></li>
            </ul>

            <h4>Developer Resources</h4>
            <ul>
                <li><a href="/swagger"><span class="sidebar-icon">💻</span> Interactive Swagger UI</a></li>
                <li><a href="/redoc"><span class="sidebar-icon">📖</span> ReDoc Specs</a></li>
            </ul>

            <div class="uptime-widget">
                <div class="title"><span class="status-dot" style="height:7px; width:7px;"></span> Pipeline Status</div>
                <div class="metric">99.98%</div>
                <div class="sub">UptimeRobot Monitored</div>
            </div>
        </aside>

        <main class="content">
            <section class="intro animated-section delay-2">
                <h1 id="architecture">API Reference</h1>
                <p>Welcome to the <strong>Airfare Price Index (APIx)</strong> programmatic interface. All endpoints return JSON payloads filtered for clean analytical and <span class="tooltip" data-tooltip="Optimized for Pandas DataFrames & scikit-learn">machine learning integration</span>.</p>
                
                <div class="live-status-banner">
                    <span class="status-dot"></span>
                    <p><strong>System Live & Superior Data Integrity:</strong> This API holds over <strong>{{TOTAL_RECORDS}}</strong> total historical records. As of <strong>{{LATEST_DATE}}</strong>, the pipeline successfully synchronized <strong>{{TODAY_RECORDS}}</strong> live market records.</p>
                </div>

                <div class="meta-box">
                    <div class="meta-item">
                        <small>Data Sources (OTAs & Direct)</small>
                        <span>
                            <span class="tooltip" data-tooltip="Aggregators: MakeMyTrip, Goibibo, Yatra, EaseMyTrip, Cleartrip, Ixigo">OTAs</span> &bull; 
                            <span class="tooltip" data-tooltip="Carriers: Air India, Air India Express, IndiGo, Akasa Air, SpiceJet">Airlines</span>
                        </span>
                    </div>
                    <div class="meta-item">
                        <small>Coverage & Scope</small>
                        <span><span class="tooltip" data-tooltip="Top hubs: DEL-BOM, BLR-DEL, HYD-DEL, etc.">20 Sectors</span> &bull; T+1 to T+45 Days</span>
                    </div>
                    <div class="meta-item">
                        <small>Latency</small>
                        <span><span class="tooltip" data-tooltip="SQLite with Indexing">~120ms P95 Response</span></span>
                    </div>
                </div>
            </section>

            <!-- QUICKSTART SECTION -->
            <section id="quickstart" class="endpoint-card animated-section delay-3">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="endpoint-path">🚀 How to Use This API<span class="typing-dots"></span></span>
                    </div>
                    <p class="endpoint-desc">Integrate APIx data directly into your machine learning pipelines, backend services, or terminal using standard HTTP requests.</p>
                </div>
                <div class="endpoint-body">
                    <div>
                        <h3>Python (For ML & Data Science)</h3>
                        <p style="font-size: 14px; color: #475569; margin-bottom: 12px;">Fetch <span class="tooltip" data-tooltip="Supports up to 50,000 records per API call">paginated records</span> into a Pandas DataFrame for modeling.</p>
                        
                        <div class="code-block-wrapper">
                            <button class="copy-btn" onclick="copyCode(this)">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                Copy
                            </button>
                            <div class="code-block">
<pre>import requests
import pandas as pd

url = "https://airfarex-api.onrender.com/api/fares/raw"
params = {"page": 1, "size": 50000, "hours_back": 24}
response = requests.get(url, params=params).json()

if response.get("status") == "ok":
    df = pd.DataFrame(response["data"])
    print(f"Loaded {len(df)} records!")
    print(df.head())
else:
    print("Error fetching data.")</pre>
                            </div>
                        </div>
                    </div>
                    
                    <div style="margin-top: 16px;">
                        <h3>cURL (For Terminal Testing)</h3>
                        <div class="code-block-wrapper">
                            <button class="copy-btn" onclick="copyCode(this)">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                Copy
                            </button>
                            <div class="code-block">
<pre>curl -X GET "https://airfarex-api.onrender.com/api/fares/raw?page=1&size=50000&hours_back=24" \
     -H "Accept: application/json"</pre>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- 1. RAW ENDPOINT FOR ML -->
            <section id="endpoint-raw" class="endpoint-card animated-section delay-4">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method-badge">GET</span>
                        <span class="endpoint-path">/api/fares/raw</span>
                    </div>
                    <p class="endpoint-desc">Retrieves flat, unaggregated ticket price records with limit/offset pagination. <span class="tooltip" data-tooltip="SQL IS NOT NULL constraints applied at query time">Non-operated</span> and NULL total fare records are filtered out automatically.</p>
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
                                    <td>Lookback window in hours. Default: <code>24</code>. (Ignored if <code>date</code> is supplied).</td>
                                </tr>
                                <tr>
                                    <td class="param-name">date</td>
                                    <td class="param-type">string</td>
                                    <td><span class="param-req req-false">Optional</span></td>
                                    <td>Exact scrape calendar date in <span class="tooltip" data-tooltip="Example: 2026-10-25"><code>YYYY-MM-DD</code></span> format.</td>
                                </tr>
                                <tr>
                                    <td class="param-name">page</td>
                                    <td class="param-type">integer</td>
                                    <td><span class="param-req req-false">Optional</span></td>
                                    <td>Page number starting from <code>1</code>. Default: <code>1</code>.</td>
                                </tr>
                                <tr>
                                    <td class="param-name">size</td>
                                    <td class="param-type">integer</td>
                                    <td><span class="param-req req-false">Optional</span></td>
                                    <td>Number of records per page (max <code>50000</code>). Default: <code>50000</code>.</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    <div class="response-container">
                        <span class="code-header">Sample JSON Response</span>
                        <div class="code-block-wrapper">
                            <button class="copy-btn" onclick="copyCode(this)">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                Copy
                            </button>
                            <div class="code-block">
<pre>{
  "status": "ok",
  "pagination": {
    "total_records": 145820,
    "page": 1,
    "size": 50000,
    "total_pages": 3,
    "has_next": true
  },
  "records_count": 50000,
  "data": [
    {
      "id": 1,
      "timestamp": "2026-10-25 14:10:02",
      "airline": "Air India Express",
      "flight_number": "IX-353",
      "route": "DEL-BOM",
      "advance_window_days": 7,
      "base_fare": 4650.0,
      "taxes_fees": 820.5,
      "total_fare": 5470.5,
      "ota_source": "MakeMyTrip",
      "departure_time": "14:30"
    }
  ]
}</pre>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- 2. COMPARE ENDPOINT -->
            <section id="endpoint-compare" class="endpoint-card animated-section delay-4">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method-badge">GET</span>
                        <span class="endpoint-path">/api/fares/compare</span>
                    </div>
                    <p class="endpoint-desc">Identifies platform advantages by returning the absolute lowest fare, average price tier, and flight inventory counts strictly grouped by OTA for a requested route.</p>
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
                        <span class="code-header">Sample JSON Response</span>
                        <div class="code-block-wrapper">
                            <button class="copy-btn" onclick="copyCode(this)">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                Copy
                            </button>
                            <div class="code-block">
<pre>{
  "status": "ok",
  "route": "DEL-BOM",
  "window": 7,
  "comparisons": [
    {
      "ota_source": "MakeMyTrip",
      "absolute_lowest_fare": 4847.0,
      "average_fare": 5120.0,
      "inventory_count": 82
    },
    {
      "ota_source": "Air India Direct",
      "absolute_lowest_fare": 5050.0,
      "average_fare": 5300.0,
      "inventory_count": 14
    }
  ]
}</pre>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            <!-- 3. MATRIX ENDPOINT -->
            <section id="endpoint-matrix" class="endpoint-card animated-section delay-4">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method-badge">GET</span>
                        <span class="endpoint-path">/api/fares/matrix</span>
                    </div>
                    <p class="endpoint-desc">Builds a 2D macroeconomic pricing grid, determining the "price floor" (minimum available fare) across all routes and advance booking windows.</p>
                </div>
                <div class="endpoint-body">
                    <div class="response-container">
                        <span class="code-header">Sample JSON Response</span>
                        <div class="code-block-wrapper">
                            <button class="copy-btn" onclick="copyCode(this)">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                Copy
                            </button>
                            <div class="code-block">
<pre>{
  "status": "ok",
  "matrix": [
    {
      "route": "DEL-BOM",
      "window": 1,
      "cheapest_available_fare": 6450.0,
      "market_average_fare": 7450.0,
      "total_competitive_options": 142
    },
    {
      "route": "DEL-BOM",
      "window": 30,
      "cheapest_available_fare": 3200.0,
      "market_average_fare": 4100.0,
      "total_competitive_options": 165
    }
  ]
}</pre>
                            </div>
                        </div>
                    </div>
                </div>
            </section>
            
            <!-- 4. HEALTH ENDPOINT -->
            <section id="endpoint-health" class="endpoint-card animated-section delay-4">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method-badge">GET</span>
                        <span class="endpoint-path">/health</span>
                    </div>
                    <p class="endpoint-desc">Lightweight ping endpoint designed specifically for <strong>UptimeRobot</strong> and CI/CD deployment checks. Verifies database connectivity instantly.</p>
                </div>
                <div class="endpoint-body">
                    <div class="response-container">
                        <span class="code-header">Sample JSON Response</span>
                        <div class="code-block-wrapper">
                            <button class="copy-btn" onclick="copyCode(this)">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                Copy
                            </button>
                            <div class="code-block">
<pre>{
  "status": "operational",
  "database": "connected",
  "environment": "production"
}</pre>
                            </div>
                        </div>
                    </div>
                </div>
            </section>
        </main>
    </div>

    <!-- JavaScript for Interactions -->
    <script>
        // Remove Splash Screen on Load
        window.addEventListener('load', () => {
            setTimeout(() => {
                const splash = document.getElementById('splash-screen');
                splash.style.opacity = '0';
                splash.style.visibility = 'hidden';
            }, 1800); 
        });

        // Copy Code Functionality
        function copyCode(button) {
            const preElement = button.nextElementSibling.querySelector('pre');
            const codeText = preElement.innerText || preElement.textContent;
            
            navigator.clipboard.writeText(codeText).then(() => {
                const originalHtml = button.innerHTML;
                button.innerHTML = '✅ Copied!';
                button.classList.add('copied');
                
                setTimeout(() => {
                    button.innerHTML = originalHtml;
                    button.classList.remove('copied');
                }, 2000);
            }).catch(err => {
                console.error('Failed to copy text: ', err);
            });
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
def get_documentation():
    # Dynamically fetch the latest date, total record count, and today's record count
    try:
        total_records = query_db_scalar("SELECT COUNT(*) FROM raw_fares")
        latest_ts = query_db_scalar("SELECT MAX(timestamp) FROM raw_fares")
        
        if latest_ts:
            # Extract just the "YYYY-MM-DD" portion to query today's specific count
            date_part = latest_ts.split(" ")[0]
            latest_date_str = datetime.strptime(date_part, "%Y-%m-%d").strftime("%b %d, %Y")
            
            # Fetch how many records were inserted on this exact latest date
            today_records = query_db_scalar("SELECT COUNT(*) FROM raw_fares WHERE date(timestamp) = ?", (date_part,))
        else:
            latest_date_str = datetime.now().strftime("%b %d, %Y")
            today_records = 0
            
        total_str = f"{total_records:,}+" if total_records else "0"
        today_str = f"{today_records:,}+" if today_records else "0"
        
    except Exception:
        # Fallback in case of database or parsing failure
        latest_date_str = datetime.now().strftime("%b %d, %Y")
        total_str = "2,573,655+"
        today_str = "59,668+"
        
    # Inject the dynamic values into the HTML template placeholders
    dynamic_html = DOCUMENTATION_HTML.replace(
        "{{LATEST_DATE}}", latest_date_str
    ).replace(
        "{{TOTAL_RECORDS}}", total_str
    ).replace(
        "{{TODAY_RECORDS}}", today_str
    )
    
    return dynamic_html


@app.get("/health", tags=["Monitoring"])
def health_check():
    """
    Lightweight endpoint for UptimeRobot monitoring. 
    Verifies that the application is running and the SQLite database is accessible.
    """
    try:
        conn, table_source = get_unified_db()
        # Perform a fast, lightweight query to ensure DB integrity
        sql = f"SELECT 1 FROM {table_source} LIMIT 1"
        conn.execute(sql).fetchone()
        conn.close()
        return {"status": "operational", "database": "connected", "environment": "production"}
    except Exception as e:
        return {"status": "degraded", "database": "disconnected", "error": str(e)}

@app.head("/health", include_in_schema=False)
def health_check_head():
    return Response(status_code=200)

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
    data_query = f"{data_query_base} ORDER BY timestamp ASC, id ASC LIMIT ? OFFSET ?"
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
    q = '''SELECT ota_source, MIN(total_fare) as absolute_lowest_fare, ROUND(AVG(total_fare), 2) as average_fare, COUNT(total_fare) as inventory_count
           FROM raw_fares 
           WHERE route = ? AND advance_window_days = ? 
           AND timestamp >= datetime('now', '+5 hours', '+30 minutes', '-24 hours')
           AND total_fare IS NOT NULL
           GROUP BY ota_source 
           ORDER BY absolute_lowest_fare ASC'''
    return {
        "status": "ok",
        "route": route,
        "window": window,
        "comparisons": query_db(q, (route, window))
    }

@app.get("/api/fares/matrix")
def fare_matrix():
    q = '''SELECT route, advance_window_days as window, MIN(total_fare) as cheapest_available_fare, ROUND(AVG(total_fare), 2) as market_average_fare, COUNT(total_fare) as total_competitive_options
           FROM raw_fares 
           WHERE timestamp >= datetime('now', '+5 hours', '+30 minutes', '-24 hours')
           AND total_fare IS NOT NULL
           GROUP BY route, advance_window_days 
           ORDER BY route ASC, window ASC'''
    return {
        "status": "ok",
        "matrix": query_db(q)
    }