from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import sqlite3
import time
import os

def is_already_scraped(route, window, source):
    if os.environ.get("FORCE_RESCRAPE") == "1":
        return False
    with sqlite3.connect('airfare_index.db') as conn:
        c = conn.cursor()
        try:
            c.execute("""
                SELECT COUNT(*) FROM raw_fares 
                WHERE route = ? AND advance_window_days = ? AND ota_source = ? 
                AND date(timestamp) = date(datetime('now', '+5 hours', '+30 minutes'))
            """, (route, window, source))
            return c.fetchone()[0] > 0
        except sqlite3.OperationalError:
            return False

def run_yatra_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    print("Launching Yatra Multi-Route Scraper (Clean Heading Airline Extraction & Lazy-Load)...")

    with Stealth().use_sync(sync_playwright()) as p:
        # --- DYNAMIC HEADLESS INJECTION ---
        browser = p.chromium.launch(
            headless=(os.environ.get("HEADLESS_MODE") == "1"), 
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        print("Initializing Yatra gateway session...")
        warmup = context.new_page()
        try:
            warmup.goto("https://www.yatra.com", timeout=30000)
            warmup.wait_for_timeout(3000)
        except Exception:
            pass
        finally:
            warmup.close()

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                if is_already_scraped(route, window, "Yatra"):
                    print(f"⏩ Yatra: {route} | T+{window} already collected today. Skipping.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d/%m/%Y")
                print(f"\n--- Yatra Scraping: {route} | T+{window} Days ({date_str}) ---")
                
                for attempt in range(1, 3):
                    page = context.new_page() 
                    try:
                        url = f"https://flight.yatra.com/air-search-ui/dom2/trigger?type=O&viewName=normal&flexi=0&noOfSegments=1&origin={origin}&originCountry=IN&destination={dest}&destinationCountry=IN&flight_depart_date={date_str}&ADT=1&CHD=0&INF=0&class=Economy&source=fresco-home"
                        page.goto(url, wait_until="domcontentloaded", timeout=50000)
                        
                        flights_loaded = False
                        for _ in range(40): 
                            try:
                                body_text = page.locator("body").inner_text()
                                if "Akamai" in body_text or "waiting" in body_text.lower():
                                    page.wait_for_timeout(1000)
                                    continue
                                if body_text.count("₹") > 4 or body_text.count("Rs") > 4:
                                    flights_loaded = True
                                    break
                            except Exception:
                                page.wait_for_timeout(1000)
                                continue
                            page.wait_for_timeout(1000)
                        
                        if not flights_loaded:
                            raise Exception("Flights not rendered after Akamai redirect.")
                            
                        print("Page loaded. Executing scroll loop to trigger all lazy-rendered flight cards...")
                        for step in range(18):
                            page.evaluate("window.scrollBy(0, 1200);")
                            page.wait_for_timeout(800)
                            
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                        page.wait_for_timeout(2000)
                            
                        # --- JAVASCRIPT DEEP EXTRACTION ---
                        valid_flights = page.evaluate(f"""() => {{
                            let records = [];
                            let cards = document.querySelectorAll('.flightItem, div[class*="flightItem"]');
                            
                            cards.forEach(card => {{
                                let text = card.innerText || "";
                                
                                // 1. Strict Origin & Destination Check via Exact Inspect Nodes
                                let origNode = card.querySelector('.mob-origin');
                                let destNode = card.querySelector('.arrival-details .mob-origin');
                                
                                let cardOrig = "";
                                let cardDest = "";
                                
                                if (origNode && destNode) {{
                                    let origMatch = origNode.innerText.match(/\\(([A-Z]{{3}})\\)/);
                                    let destMatch = destNode.innerText.match(/\\(([A-Z]{{3}})\\)/);
                                    if (origMatch) cardOrig = origMatch[1];
                                    if (destMatch) cardDest = destMatch[1];
                                }}
                                
                                if (cardOrig !== '{origin}' || cardDest !== '{dest}') {{
                                    return;
                                }}
                                
                                // 2. Extract Pure Airline Name using heading span
                                let airlineEl = card.querySelector('span[role="heading"]');
                                let airline = airlineEl ? (airlineEl.getAttribute('title') || airlineEl.innerText.trim()) : "Yatra Partner";
                                
                                // 3. Extract Flight Number
                                let flNoEl = card.querySelector('.fl-no span, .font-lightgrey.fl-no');
                                let flightNo = flNoEl ? flNoEl.innerText.trim() : "";
                                if (!flightNo) {{
                                    let m = text.match(/([A-Z0-9]{{2}}[\\-\\s]?\\d{{3,4}})/);
                                    flightNo = m ? m[1].replace(/\\s+/, '-') : "UNKNOWN";
                                }} else {{
                                    flightNo = flightNo.replace(/\\s+/, '-');
                                }}
                                
                                // 4. Extract Departure Time
                                let timeEl = card.querySelector('.mob-time');
                                let depTime = timeEl ? timeEl.innerText.trim() : "";
                                if (!depTime) {{
                                    let tMatch = text.match(/\\b(\\d{{2}}:\\d{{2}})\\b/);
                                    depTime = tMatch ? tMatch[0] : "00:00";
                                }}
                                
                                // 5. Extract Price
                                let priceEl = card.querySelector('.ow-price-above-btn, .price');
                                let cleanPrice = 0;
                                if (priceEl && priceEl.innerText) {{
                                    cleanPrice = parseInt(priceEl.innerText.replace(/[^0-9]/g, ''));
                                }} else {{
                                    let pMatch = text.match(/[₹|Rs]\\s*([\\d,]+)/);
                                    if (pMatch) cleanPrice = parseInt(pMatch[1].replace(/,/g, ''));
                                }}
                                
                                if (!isNaN(cleanPrice) && cleanPrice > 1000 && flightNo) {{
                                    records.push({{
                                        airline: airline,
                                        flight_no: flightNo,
                                        departure_time: depTime,
                                        fare: cleanPrice
                                    }});
                                }}
                            }});
                            
                            // Deduplicate
                            let unique = {{}};
                            records.forEach(r => {{
                                let key = r.flight_no + "_" + r.departure_time;
                                if (!unique[key] || r.fare < unique[key].fare) {{
                                    unique[key] = r;
                                }}
                            }});
                            return Object.values(unique);
                        }}""")
                        
                        if valid_flights:
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.execute('''
                                    CREATE TABLE IF NOT EXISTS raw_fares (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                        airline TEXT, route TEXT, advance_window_days INTEGER, base_fare REAL, 
                                        taxes_fees REAL, total_fare REAL, ota_source TEXT, departure_time TEXT, flight_no TEXT
                                    )
                                ''')
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', [(
                                    f['airline'], 
                                    route, 
                                    window, 
                                    round(f['fare'] * 0.85, 2), 
                                    round(f['fare'] * 0.15, 2), 
                                    f['fare'], 
                                    "Yatra", 
                                    f['departure_time'], 
                                    f['flight_no']
                                ) for f in valid_flights])  
                                conn.commit()
                            print(f"✅ Saved {len(valid_flights)} verified records (Attempt {attempt}).")
                            page.close()
                            break
                        else:
                            raise Exception("Zero valid flights matched route criteria.")
                                        
                    except Exception as e:
                        print(f"⚠️ Yatra Attempt {attempt} failed: {e}")
                        page.close()
                        if attempt == 1:
                            time.sleep(5)
                    
                time.sleep(2)

        browser.close()
        print("\n🎉 Yatra Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_yatra_scraper()