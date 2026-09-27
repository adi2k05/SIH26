from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import sqlite3
import re
import time
import os

def is_already_scraped(route, window, source):
    if os.environ.get("FORCE_RESCRAPE") == "1":
        return False
    if not os.path.exists('airfare_index.db'):
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

def run_ixigo_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    print("Launching Ixigo Scraper (All Flights & Strict Route Filters Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(
            headless=False, 
            args=["--disable-blink-features=AutomationControlled"]
        )

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                if is_already_scraped(route, window, "Ixigo"):
                    print(f"⏩ Ixigo: {route} | T+{window} already collected today. Skipping.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d%m%Y")
                
                # --- NATIVE URL WITHOUT NON-STOP FLAG ---
                search_url = f"https://www.ixigo.com/search/result/flight?from={origin}&to={dest}&date={date_str}&adults=1&children=0&infants=0&class=e"
                
                print(f"\n--- Ixigo Scraping: {route} | T+{window} Days ({date_str}) ---")
                
                for attempt in range(1, 3):
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        viewport={"width": 1920, "height": 1080}
                    )
                    page = context.new_page() 
                    
                    try:
                        page.goto(search_url, timeout=60000)
                        page.wait_for_timeout(5000) 
                        
                        print("Waiting for results to render...")
                        loaded = False
                        for _ in range(30):
                            body_text = page.locator("body").inner_text()
                            if "₹" in body_text or "Rs" in body_text:
                                loaded = True
                                break
                            if "no flights" in body_text.lower() or "sold out" in body_text.lower() or "no results" in body_text.lower():
                                loaded = "EMPTY"
                                break
                            page.wait_for_timeout(1000)
                        
                        if not loaded:
                            raise Exception("Timeout waiting for flights to render.")
                        
                        if loaded == "EMPTY":
                            print(f"ℹ️ Ixigo officially returned no flights for T+{window}. Logging NULL.")
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.execute('''
                                    CREATE TABLE IF NOT EXISTS raw_fares (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                        airline TEXT, route TEXT, advance_window_days INTEGER, base_fare REAL, 
                                        taxes_fees REAL, total_fare REAL, ota_source TEXT, departure_time TEXT, flight_no TEXT
                                    )
                                ''')
                                conn.execute('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                    VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?, NULL)
                                ''', ("Unknown", route, window, "Ixigo", "TBD"))
                                conn.commit()
                            context.close()
                            break 
                        
                        print("Scrolling to load all flights...")
                        seen_flights = set()
                        route_data = []
                        
                        # --- UPDATED JAVASCRIPT EXTRACTOR ---
                        js_extractor = f"""
                        () => {{
                            let results = [];
                            let priceElements = document.querySelectorAll('[data-testid="pricing"]');
                            
                            priceElements.forEach(priceEl => {{
                                let card = priceEl.closest('div[class*="shadow-sm"], div[class*="border-"], div[class*="tile"], div[class*="card"]') || priceEl.parentElement;
                                if (!card) return;

                                let cardText = card.innerText || "";
                                let lowerText = cardText.toLowerCase();
                                let lines = cardText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

                                // 1. Strict Origin & Destination Check Native to DOM
                                let validRoute = false;
                                
                                // Target the exact 'p' tags inside 'timeTileList' elements based on inspector
                                let airportNodes = card.querySelectorAll('div[class*="timeTileList"] p[class*="body-sm"]');
                                
                                if (airportNodes && airportNodes.length >= 2) {{
                                    // First node is Origin, Last node is Destination
                                    let cardOrig = airportNodes[0].innerText.trim().toUpperCase();
                                    let cardDest = airportNodes[airportNodes.length - 1].innerText.trim().toUpperCase();

                                    // Exact string match (e.g. 'DEL' === 'DEL') rejects 'NMI'/'HDO' natively
                                    if (cardOrig === '{origin}' && cardDest === '{dest}') {{
                                        validRoute = true;
                                    }}
                                }} else {{
                                    // Fallback: check whole card and strictly block alternate airports
                                    let hasOrigin = lines.some(l => new RegExp("\\\\b{origin}\\\\b", "i").test(l));
                                    let hasDest = lines.some(l => new RegExp("\\\\b{dest}\\\\b", "i").test(l));
                                    if (hasOrigin && hasDest) {{
                                        if (!lowerText.includes('navi mumbai') && !lowerText.includes('ghaziabad') && 
                                            !lowerText.includes('hindon') && !lowerText.includes('noida') && 
                                            !lowerText.includes('nmi') && !lowerText.includes('hdo')) {{
                                            validRoute = true;
                                        }}
                                    }}
                                }}
                                
                                if (!validRoute) return;

                                // 2. Extract Price
                                let cleanPrice = parseInt((priceEl.innerText || "").replace(/[^0-9]/g, ''));
                                if (isNaN(cleanPrice) || cleanPrice < 1000) return;

                                // 3. Extract Airline & Flight Num
                                let flightNum = "";
                                let airline = "Unknown";
                                
                                for (let i = 0; i < Math.min(10, lines.length); i++) {{
                                    if (/^[A-Z0-9]{{2}}[\\-\\s]?\\d{{3,4}}/i.test(lines[i])) {{
                                        flightNum = lines[i].replace(/\\s+/g, '-');
                                        if (i > 0) airline = lines[i-1]; 
                                        break;
                                    }}
                                }}
                                
                                // 4. Extract Departure Time Natively via .text-primary h6
                                let depTime = "Unknown";
                                let timeNode = card.querySelector('h6[class*="text-primary"], .timeTileList h6');
                                if (timeNode && /\\d{{2}}:\\d{{2}}/.test(timeNode.innerText)) {{
                                    let match = timeNode.innerText.match(/\\b(\\d{{2}}:\\d{{2}})\\b/);
                                    if (match) depTime = match[0];
                                }} else {{
                                    let times = cardText.match(/\\b(\\d{{2}}:\\d{{2}})\\b/g) || [];
                                    if (times.length > 0) depTime = times[0];
                                }}
                                
                                if (flightNum) {{
                                    results.push({{ 
                                        airline: airline, 
                                        flight_number: flightNum, 
                                        departure_time: depTime, 
                                        total_fare: cleanPrice 
                                    }});
                                }}
                            }});
                            return results;
                        }}
                        """
                        
                        scroll_attempts = 0
                        max_scrolls = 30
                        last_flight_count = 0
                        stagnant_scrolls = 0
                        
                        while scroll_attempts < max_scrolls:
                            current_flights = page.evaluate(js_extractor)
                            
                            for f in current_flights:
                                uniq_key = f"{f['flight_number']}_{f['departure_time']}_{f['total_fare']}"
                                if uniq_key not in seen_flights:
                                    seen_flights.add(uniq_key)
                                    base_fare = round(f['total_fare'] * 0.85, 2)
                                    taxes_fees = round(f['total_fare'] * 0.15, 2)
                                    
                                    route_data.append((
                                        f['airline'], route, window, 
                                        base_fare, taxes_fees, f['total_fare'], "Ixigo", f['departure_time'], f['flight_number']
                                    ))
                            
                            if len(seen_flights) == last_flight_count:
                                stagnant_scrolls += 1
                                if stagnant_scrolls >= 3:
                                    break 
                            else:
                                stagnant_scrolls = 0
                                
                            last_flight_count = len(seen_flights)
                            
                            page.mouse.move(960, 540)
                            page.mouse.wheel(0, 1500)
                            page.keyboard.press("PageDown")
                            page.wait_for_timeout(1200)
                            scroll_attempts += 1
                        
                        if route_data:
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
                                ''', route_data)
                                conn.commit()
                                
                            print(f"✅ Saved {len(route_data)} verified unique records (Attempt {attempt}).")
                            context.close()
                            break 
                        else:
                            raise Exception("Zero valid flights extracted.")
                                        
                    except Exception as e:
                        print(f"⚠️ Ixigo Attempt {attempt} failed: {e}")
                        context.close()
                        if attempt == 1:
                            time.sleep(5)
                    
                time.sleep(3)

        browser.close()
        print("\n🎉 Ixigo Scraping Complete!")

if __name__ == "__main__":
    run_ixigo_scraper()