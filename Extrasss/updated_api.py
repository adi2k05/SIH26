from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from typing import Optional
from datetime import datetime, timedelta
import sqlite3
import math
import glob
import io
import csv

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
            --map-bg: #0d1117;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background-color: var(--bg-main);
            color: var(--text-dark);
            line-height: 1.6;
            overflow-x: hidden;
            scroll-behavior: smooth;
        }
        
        /* --- SPLASH SCREEN ANIMATION --- */
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
        
        /* --- HIGH-END ANIMATIONS & EFFECTS --- */
        @keyframes fadeSlideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse-green { 0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); } 70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); } 100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); } }
        @keyframes float { 0%, 100% { transform: translateY(0) rotate(0deg); } 50% { transform: translateY(-3px) rotate(4deg); } }
        @keyframes typing { 0%, 20% { content: '.'; } 40%, 60% { content: '..'; } 80%, 100% { content: '...'; } }
        @keyframes dash { to { stroke-dashoffset: 0; } }
        @keyframes flow { from { stroke-dashoffset: 24; } to { stroke-dashoffset: 0; } }

        .animated-section { animation: fadeSlideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards; opacity: 0; }
        .delay-1 { animation-delay: 0.1s; }
        .delay-2 { animation-delay: 0.2s; }
        .delay-3 { animation-delay: 0.3s; }
        .delay-4 { animation-delay: 0.4s; }

        .status-dot {
            height: 9px; width: 9px; background-color: #10b981; border-radius: 50%; 
            display: inline-block; margin-right: 8px; animation: pulse-green 2s infinite;
        }
        .float-emoji { display: inline-block; animation: float 4s ease-in-out infinite; }
        .typing-dots::after { content: '.'; display: inline-block; width: 1em; text-align: left; animation: typing 1.5s infinite; }

        /* Layout & Components */
        header {
            background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border); padding: 16px 48px;
            display: flex; align-items: center; justify-content: space-between;
            position: sticky; top: 0; z-index: 100; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
        }
        .brand { display: flex; align-items: center; font-weight: 700; font-size: 1.15rem; color: #0f172a; }
        .badge-version {
            background: #e0f2fe; color: #0369a1; font-size: 11px; padding: 3px 8px;
            border-radius: 999px; font-weight: 700; margin-left: 12px; border: 1px solid #bae6fd;
        }
        .nav-links { display: flex; gap: 8px; }
        .nav-links a {
            color: #475569; text-decoration: none; font-size: 13.5px; font-weight: 600;
            padding: 8px 14px; border-radius: 8px; transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .nav-links a:hover { background: #f1f5f9; color: #0f172a; }
        
        .container {
            max-width: 1320px; margin: 0 auto; padding: 40px 24px 80px;
            display: grid; grid-template-columns: 260px 1fr; gap: 56px;
        }
        
        .sidebar { position: sticky; top: 100px; height: fit-content; padding-right: 16px; }
        .sidebar h4 { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #94a3b8; margin-bottom: 12px; font-weight: 700; margin-top: 24px;}
        .sidebar h4:first-child { margin-top: 0; }
        .sidebar ul { list-style: none; margin-bottom: 8px; }
        .sidebar li { margin-bottom: 2px; }
        .sidebar a {
            display: flex; align-items: center; gap: 10px;
            color: #475569; text-decoration: none; font-size: 13.5px;
            padding: 8px 12px; border-radius: 6px; transition: all 0.2s;
            font-weight: 500; border-left: 3px solid transparent;
        }
        .sidebar a:hover {
            background: #f1f5f9; color: var(--primary-dark);
            border-left: 3px solid var(--primary); transform: translateX(2px);
        }
        
        .uptime-widget { margin-top: 32px; padding: 16px; border-radius: 8px; background: #f8fafc; border: 1px solid var(--border); }
        .uptime-widget .title { font-size: 12px; font-weight: 700; color: #475569; display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
        .uptime-widget .metric { font-size: 20px; font-weight: 800; color: #0f172a; font-family: 'JetBrains Mono', monospace; }
        .uptime-widget .sub { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

        .content { display: flex; flex-direction: column; gap: 40px; }
        
        .intro h1 { 
            font-size: 2.6rem; font-weight: 800; margin-bottom: 12px; letter-spacing: -0.02em;
            background: linear-gradient(90deg, #0f172a, #2563eb); -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .intro p { color: #475569; font-size: 1.1rem; line-height: 1.7; }
        
        .live-status-banner {
            margin-top: 24px; padding: 18px 24px; background: linear-gradient(145deg, #ecfdf5 0%, #ffffff 100%);
            border: 1px solid #a7f3d0; border-left: 4px solid #10b981; border-radius: 8px;
            display: flex; align-items: center; gap: 16px; box-shadow: 0 4px 6px -1px rgba(16, 185, 129, 0.05);
        }
        .live-status-banner p { margin: 0; font-size: 14.5px; color: #064e3b; font-weight: 500; line-height: 1.6; }
        .live-status-banner strong { font-weight: 700; color: #047857; }

        /* Route Basket Map (SIH Dark Theme) */
        .route-map-container {
            background: var(--map-bg); border-radius: 12px; padding: 24px;
            border: 1px solid #30363d; overflow: hidden; position: relative;
            box-shadow: inset 0 2px 20px rgba(0,0,0,0.5);
        }
        .route-map-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
        .rm-title { color: #f0f6fc; font-size: 16px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; display: flex; align-items: center; gap: 8px;}
        .rm-title::before { content: ''; display: inline-block; width: 12px; height: 12px; background: #ea580c; border-radius: 50%; box-shadow: 0 0 10px #ea580c; }
        .rm-subtitle { color: #8b949e; font-size: 12px; margin-top: 4px; }
        .rm-stats { text-align: right; background: rgba(255,255,255,0.05); padding: 12px 16px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1);}
        .rm-stats-main { color: #10b981; font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: 700; }
        .rm-stats-sub { color: #8b949e; font-size: 11px; margin-top: 4px; }
        
        .svg-map { width: 100%; height: 350px; }
        .map-node { fill: #38bdf8; transition: all 0.3s; cursor: pointer; }
        .map-node:hover { fill: #ffffff; r: 6; }
        .map-label { fill: #8b949e; font-size: 10px; font-family: 'Inter', sans-serif; font-weight: 600; pointer-events: none; }
        .map-path { stroke: rgba(56, 189, 248, 0.3); stroke-width: 1.5; fill: none; stroke-dasharray: 4 4; animation: flow 20s linear infinite; }
        .map-path-highlight { stroke: #ea580c; stroke-width: 2.5; fill: none; filter: drop-shadow(0 0 4px rgba(234, 88, 12, 0.6)); stroke-dasharray: 1000; stroke-dashoffset: 1000; animation: dash 2s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
        
        /* CSV Exporter UI */
        .csv-exporter {
            background: #ffffff; border: 1px solid var(--border); border-radius: 12px;
            padding: 24px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02); margin-bottom: 20px;
        }
        .csv-header { margin-bottom: 20px; }
        .csv-header h3 { color: #0f172a; font-size: 16px; margin-bottom: 4px; font-weight: 700; }
        .csv-header p { color: #64748b; font-size: 13.5px; }
        .csv-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .input-group { display: flex; flex-direction: column; gap: 6px; }
        .input-group label { font-size: 12px; font-weight: 600; color: #475569; text-transform: uppercase; letter-spacing: 0.02em; }
        .input-group select {
            padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 6px;
            font-size: 14px; font-family: 'Inter', sans-serif; color: #0f172a;
            background-color: #f8fafc; outline: none; transition: border-color 0.2s;
        }
        .input-group select:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
        .btn-download {
            background: var(--primary); color: white; border: none; padding: 12px 24px;
            border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer;
            transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%;
        }
        .btn-download:hover { background: var(--primary-dark); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(37,99,235,0.2); }

        .endpoint-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.03); overflow: hidden; margin-bottom: 40px;}
        .endpoint-header { padding: 24px; border-bottom: 1px solid var(--border); background: #f8fafc; }
        .endpoint-title { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
        .method-badge { background: var(--get-bg); color: var(--get-color); font-weight: 700; font-size: 12px; padding: 4px 10px; border-radius: 6px; font-family: 'JetBrains Mono', monospace; }
        .endpoint-path { font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 1.1rem; color: #0f172a; }
        .endpoint-desc { color: #475569; font-size: 14.5px; }
        .endpoint-body { padding: 24px; display: flex; flex-direction: column; gap: 24px; }
        h3 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); margin-bottom: 12px; font-weight: 700; }
        table { width: 100%; border-collapse: collapse; font-size: 13.5px; text-align: left; }
        th { background: #f1f5f9; padding: 12px 14px; font-weight: 600; color: #334155; border-bottom: 1px solid var(--border); }
        td { padding: 14px 14px; border-bottom: 1px solid var(--border); vertical-align: top; }
        .param-name { font-family: 'JetBrains Mono', monospace; font-weight: 600; color: #0369a1; }
        
        .code-block-wrapper { position: relative; background: var(--code-bg); border-radius: 8px; overflow: hidden; }
        .copy-btn {
            position: absolute; top: 12px; right: 12px; background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.2);
            color: #e2e8f0; padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; gap: 6px; z-index: 10;
        }
        .copy-btn:hover { background: rgba(255, 255, 255, 0.2); color: #fff; }
        .code-block { padding: 20px; padding-top: 40px; font-family: 'JetBrains Mono', monospace; font-size: 13px; overflow-x: auto; color: #f8fafc; }
        .code-block code { color: #38bdf8; }
        .code-header { font-size: 12px; color: var(--text-muted); font-weight: 700; margin-bottom: 8px; display: block; text-transform: uppercase; }
    </style>
</head>
<body>
    <!-- SPLASH SCREEN -->
    <div id="splash-screen">
        <div class="loader-ring"></div>
        <div class="splash-text">AirfareX Engine Initializing...</div>
    </div>

    <header>
        <div class="brand">
            <span class="status-dot"></span> <span class="float-emoji">✈️</span> AirfareX API
            <span class="badge-version">v2.0 (SIH Analytics Engine)</span>
        </div>
        <div class="nav-links">
            <a href="#quickstart">Quickstart</a>
            <a href="#endpoint-raw">/raw (ML)</a>
            <a href="#endpoint-csv">/csv (Export)</a>
        </div>
    </header>

    <div class="container">
        <aside class="sidebar animated-section delay-1">
            <h4>Introduction</h4>
            <ul>
                <li><a href="#quickstart">🚀 Integration Guide</a></li>
                <li><a href="#architecture">⚙️ Architecture Map</a></li>
            </ul>
            
            <h4>Data Export</h4>
            <ul>
                <li><a href="#endpoint-csv">📥 Download CSV</a></li>
            </ul>
            
            <h4>Core Endpoints</h4>
            <ul>
                <li><a href="#endpoint-raw">📊 GET /fares/raw</a></li>
                <li><a href="#endpoint-compare">⚖️ GET /fares/compare</a></li>
                <li><a href="#endpoint-matrix">📈 GET /fares/matrix</a></li>
            </ul>

            <h4>Monitoring</h4>
            <ul>
                <li><a href="#endpoint-health">🩺 GET /health (Uptime)</a></li>
            </ul>

            <div class="uptime-widget">
                <div class="title"><span class="status-dot" style="height:7px; width:7px;"></span> Pipeline Status</div>
                <div class="metric">99.98%</div>
                <div class="sub">UptimeRobot Monitored</div>
            </div>
        </aside>

        <main class="content">
            <section class="intro animated-section delay-2" id="architecture">
                <h1>API Reference</h1>
                <p>Welcome to the <strong>Airfare Price Index (APIx)</strong> interface. Our endpoints return payloads specifically filtered for clean analytical and machine learning integration.</p>
                
                <div class="live-status-banner">
                    <span class="status-dot"></span>
                    <p><strong>System Live & Superior Data Integrity:</strong> Unlike static, frozen datasets, our infrastructure is continuously active. As of <strong id="live-date">Today</strong>, the pipeline has synchronized over <strong id="live-count">100,000+</strong> live market records.</p>
                </div>
            </section>

            <!-- ROUTE MAP VISUALIZATION (SIH STYLE) -->
            <section class="animated-section delay-3">
                <div class="route-map-container">
                    <div class="route-map-header">
                        <div>
                            <div class="rm-title">INDIAN DOMESTIC ROUTE BASKET</div>
                            <div class="rm-subtitle">Official AirSetu Boundaries • Top High-Density Corridors</div>
                        </div>
                        <div class="rm-stats">
                            <div class="rm-stats-main">DEL-BOM <span style="color:#8b949e; font-weight:normal; font-size:12px; margin-left:8px;">22.35% Weight</span></div>
                            <div class="rm-stats-sub">Delhi → Mumbai • 1148 km Great-Circle</div>
                        </div>
                    </div>
                    
                    <svg class="svg-map" viewBox="0 0 800 400" preserveAspectRatio="xMidYMid meet">
                        <!-- Abstract India Geography Nodes -->
                        <g transform="translate(100, 0)">
                            <!-- Connections (Faded) -->
                            <path class="map-path" d="M 250 80 Q 300 150 450 180" /> <!-- DEL to CCU -->
                            <path class="map-path" d="M 250 80 Q 280 200 280 280" /> <!-- DEL to BLR -->
                            <path class="map-path" d="M 250 80 Q 280 180 300 220" /> <!-- DEL to HYD -->
                            <path class="map-path" d="M 150 220 Q 200 250 280 280" /> <!-- BOM to BLR -->
                            
                            <!-- Highlighted Corridor (DEL-BOM) -->
                            <path class="map-path-highlight" d="M 250 80 Q 180 150 150 220" />
                            
                            <!-- City Nodes -->
                            <!-- DEL -->
                            <circle class="map-node" cx="250" cy="80" r="4"/>
                            <text class="map-label" x="260" y="84">DEL (Delhi)</text>
                            
                            <!-- BOM -->
                            <circle class="map-node" cx="150" cy="220" r="4"/>
                            <text class="map-label" x="160" y="224" fill="#ffffff">BOM (Mumbai)</text>
                            
                            <!-- AMD -->
                            <circle class="map-node" cx="120" cy="150" r="3"/>
                            <text class="map-label" x="130" y="154">AMD</text>
                            
                            <!-- GOI -->
                            <circle class="map-node" cx="160" cy="270" r="3"/>
                            <text class="map-label" x="170" y="274">GOI</text>
                            
                            <!-- BLR -->
                            <circle class="map-node" cx="280" cy="280" r="4"/>
                            <text class="map-label" x="290" y="284">BLR</text>
                            
                            <!-- HYD -->
                            <circle class="map-node" cx="300" cy="220" r="4"/>
                            <text class="map-label" x="310" y="224">HYD</text>
                            
                            <!-- MAA -->
                            <circle class="map-node" cx="320" cy="300" r="3"/>
                            <text class="map-label" x="330" y="304">MAA</text>
                            
                            <!-- CCU -->
                            <circle class="map-node" cx="450" cy="180" r="4"/>
                            <text class="map-label" x="460" y="184">CCU (Kolkata)</text>
                        </g>
                    </svg>
                </div>
            </section>

            <!-- CSV EXPORT UI -->
            <section id="endpoint-csv" class="animated-section delay-3">
                <div class="csv-exporter">
                    <div class="csv-header">
                        <h3>📥 Data Export (CSV Generator)</h3>
                        <p>Generate a clean, flat CSV file of the raw indexing data for offline pandas analysis or Excel.</p>
                    </div>
                    <div class="csv-grid">
                        <div class="input-group">
                            <label>Date From</label>
                            <select id="csv-date-from"></select>
                        </div>
                        <div class="input-group">
                            <label>Date To</label>
                            <select id="csv-date-to"></select>
                        </div>
                        <div class="input-group">
                            <label>OTA Source</label>
                            <select id="csv-ota"><option value="All">All OTAs & Direct</option></select>
                        </div>
                        <div class="input-group">
                            <label>Airline</label>
                            <select id="csv-airline"><option value="All">All Airlines</option></select>
                        </div>
                    </div>
                    <button class="btn-download" onclick="downloadCSV()">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                        Generate & Download CSV
                    </button>
                </div>
            </section>

            <!-- QUICKSTART SECTION -->
            <section id="quickstart" class="endpoint-card animated-section delay-4">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="endpoint-path">🚀 Quickstart Code<span class="typing-dots"></span></span>
                    </div>
                    <p class="endpoint-desc">Integrate APIx data directly into your machine learning pipelines.</p>
                </div>
                <div class="endpoint-body">
                    <div>
                        <h3>Python (Pandas Integration)</h3>
                        <div class="code-block-wrapper">
                            <button class="copy-btn" onclick="copyCode(this)">📋 Copy</button>
                            <div class="code-block">
<pre>import requests
import pandas as pd

url = "https://airfarex-api.onrender.com/api/fares/raw"
params = {"page": 1, "size": 50000, "hours_back": 24}
response = requests.get(url, params=params).json()

if response.get("status") == "ok":
    df = pd.DataFrame(response["data"])
    print(f"Loaded {len(df)} records!")
    print(df.head())</pre>
                            </div>
                        </div>
                    </div>
                </div>
            </section>
            
            <!-- HEALTH ENDPOINT -->
            <section id="endpoint-health" class="endpoint-card">
                <div class="endpoint-header">
                    <div class="endpoint-title">
                        <span class="method-badge">GET</span>
                        <span class="endpoint-path">/health</span>
                    </div>
                    <p class="endpoint-desc">Lightweight ping endpoint designed specifically for <strong>UptimeRobot</strong>. Verifies database connectivity instantly.</p>
                </div>
                <div class="endpoint-body">
                    <div class="response-container">
                        <span class="code-header">Sample JSON Response</span>
                        <div class="code-block-wrapper">
                            <button class="copy-btn" onclick="copyCode(this)">📋 Copy</button>
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

    <script>
        // Remove Splash Screen on Load
        window.addEventListener('load', () => {
            setTimeout(() => {
                const splash = document.getElementById('splash-screen');
                splash.style.opacity = '0';
                splash.style.visibility = 'hidden';
            }, 1800); 
            
            // Fetch metadata to populate CSV dropdowns & Banner
            fetch('/api/meta').then(res => res.json()).then(data => {
                const df = document.getElementById('csv-date-from');
                const dt = document.getElementById('csv-date-to');
                const ota = document.getElementById('csv-ota');
                const air = document.getElementById('csv-airline');
                
                // Set live banner values
                document.getElementById('live-date').innerText = data.max_date;
                document.getElementById('live-count').innerText = data.total_records.toLocaleString() + "+";
                
                // Populate Dates (from min to max)
                let curr = new Date(data.min_date);
                let end = new Date(data.max_date);
                while(curr <= end) {
                    let dStr = curr.toISOString().split('T')[0];
                    df.add(new Option(dStr, dStr));
                    dt.add(new Option(dStr, dStr));
                    curr.setDate(curr.getDate() + 1);
                }
                dt.value = data.max_date; // default To is max
                
                // Populate OTAs & Airlines
                data.otas.forEach(o => ota.add(new Option(o, o)));
                data.airlines.forEach(a => air.add(new Option(a, a)));
            }).catch(err => console.error("Error loading metadata:", err));
        });

        function downloadCSV() {
            const df = document.getElementById('csv-date-from').value;
            const dt = document.getElementById('csv-date-to').value;
            const ota = document.getElementById('csv-ota').value;
            const air = document.getElementById('csv-airline').value;
            
            let url = `/api/fares/export/csv?date_from=${df}&date_to=${dt}`;
            if(ota !== "All") url += `&ota=${encodeURIComponent(ota)}`;
            if(air !== "All") url += `&airline=${encodeURIComponent(air)}`;
            
            window.open(url, '_blank');
        }

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
            });
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/docs", response_class=HTMLResponse, include_in_schema=False)
def get_documentation():
    return DOCUMENTATION_HTML

@app.get("/health", tags=["Monitoring"])
def health_check():
    try:
        conn, table_source = get_unified_db()
        sql = f"SELECT 1 FROM {table_source} LIMIT 1"
        conn.execute(sql).fetchone()
        conn.close()
        return {"status": "operational", "database": "connected", "environment": "production"}
    except Exception as e:
        return {"status": "degraded", "database": "disconnected", "error": str(e)}

@app.get("/api/meta", tags=["Metadata"])
def get_meta():
    """Returns available date ranges, OTAs, Airlines, and total record count to populate the UI."""
    try:
        conn, table_source = get_unified_db()
        cursor = conn.cursor()
        
        cursor.execute(f"SELECT COUNT(*) FROM {table_source}")
        total = cursor.fetchone()[0]
        
        cursor.execute(f"SELECT MIN(date(timestamp)), MAX(date(timestamp)) FROM {table_source}")
        min_date, max_date = cursor.fetchone()
        
        cursor.execute(f"SELECT DISTINCT ota_source FROM {table_source} WHERE ota_source IS NOT NULL ORDER BY ota_source")
        otas = [r[0] for r in cursor.fetchall()]
        
        cursor.execute(f"SELECT DISTINCT airline FROM {table_source} WHERE airline IS NOT NULL ORDER BY airline")
        airlines = [r[0] for r in cursor.fetchall()]
        
        conn.close()
        return {
            "total_records": total or 0,
            "min_date": min_date or "2024-09-05", 
            "max_date": max_date or datetime.now().strftime("%Y-%m-%d"), 
            "otas": otas, 
            "airlines": airlines
        }
    except Exception:
        return {"total_records": 0, "min_date": "2024-09-05", "max_date": datetime.now().strftime("%Y-%m-%d"), "otas": [], "airlines": []}

@app.get("/api/fares/export/csv", tags=["Export"])
def export_csv(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    ota: Optional[str] = Query(None),
    airline: Optional[str] = Query(None)
):
    """Generates a downloadable CSV file based on the selected filters."""
    conn, table_source = get_unified_db()
    query = f"SELECT timestamp, airline, flight_no as flight_number, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time FROM {table_source} WHERE 1=1"
    params = []
    
    if date_from:
        query += " AND date(timestamp) >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date(timestamp) <= ?"
        params.append(date_to)
    if ota and ota != "All":
        query += " AND ota_source = ?"
        params.append(ota)
    if airline and airline != "All":
        query += " AND airline = ?"
        params.append(airline)
        
    query += " ORDER BY timestamp ASC LIMIT 100000" # Safety limit to prevent memory crashes

    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    col_names = [description[0] for description in cursor.description]
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(col_names)
    writer.writerows(rows)
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=airfarex_export.csv"}
    )

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