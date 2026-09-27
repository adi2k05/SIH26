from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import sqlite3
import re
import time
import os

def is_already_scraped(route, window, source):
    if os.environ.get("FORCE_RESCRAPE") == "1":
        return False
    with sqlite3.connect('airfare_index.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM raw_fares 
            WHERE route = ? AND advance_window_days = ? AND ota_source = ? 
            AND date(timestamp) = date(datetime('now', '+5 hours', '+30 minutes'))
        """, (route, window, source))
        return c.fetchone()[0] > 0

def run_akasa_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    # HARDCODED EXCLUSIONS
    # Akasa Air operates out of Manohar International (GOX), not Dabolim (GOI).
    unsupported_akasa_routes = [
        "DEL-GOI", "BOM-GOI"
    ]
    
    print("Launching Akasa Air Scraper (Native Card Targeting & Exact Span Routing)...")

    user_data_dir = os.path.join(os.getcwd(), "akasa_browser_profile")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            channel="chrome",  
            headless=False,
            viewport={"width": 1920, "height": 1080},
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            ignore_default_args=["--enable-automation"]
        )

        page = context.pages[0] if context.pages else context.new_page()

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            # --- BYPASS NON-OPERATED ROUTES INSTANTLY ---
            if route in unsupported_akasa_routes:
                print(f"ℹ️ {route} is unsupported by Akasa (operates at GOX, not GOI). Logging NULL.")
                for window in advance_windows:
                    if not is_already_scraped(route, window, "Akasa Direct"):
                        with sqlite3.connect('airfare_index.db') as conn:
                            conn.execute('''
                                INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                VALUES (?, ?, ?, NULL, NULL, NULL, ?, NULL, NULL)
                            ''', ("Akasa Air", route, window, "Akasa Direct"))
                            conn.commit()
                continue
            
            for window in advance_windows:
                if is_already_scraped(route, window, "Akasa Direct"):
                    print(f"⏩ Akasa: {route} | T+{window} already collected today. Skipping.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                print(f"\n--- Akasa Scraping: {route} | T+{window} Days ---")
                
                for attempt in range(1, 3):
                    try:
                        page.goto("https://www.akasaair.com/", wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(3500) 

                        try:
                            page.locator("button:has-text('Accept'), button:has-text('Got it'), button[aria-label='Close']").click(timeout=1500)
                        except Exception:
                            pass
                        
                        # --- ORIGIN SELECTION ---
                        loc_from = page.locator("#From")
                        loc_from.click(force=True)
                        page.wait_for_timeout(500)
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.type(origin, delay=150)
                        page.wait_for_timeout(2500)
                        
                        origin_found = page.evaluate(f'''(iata) => {{
                            let els = Array.from(document.querySelectorAll('*')).filter(e => e.textContent.trim() === iata && e.children.length === 0);
                            for(let e of els) {{ if(e.closest('div, ul, li')) {{ e.click(); return true; }} }}
                            return false;
                        }}''', origin)
                        
                        if not origin_found:
                            raise Exception(f"Origin {origin} dropdown item not found.")
                        
                        page.wait_for_timeout(2000)
                        
                        # --- DESTINATION SELECTION ---
                        loc_to = page.locator("#To")
                        loc_to.click(force=True)
                        page.wait_for_timeout(500)
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.type(dest, delay=150)
                        page.wait_for_timeout(2500)
                        
                        dest_found = page.evaluate(f'''(iata) => {{
                            let els = Array.from(document.querySelectorAll('*')).filter(e => e.textContent.trim() === iata && e.children.length === 0);
                            for(let e of els) {{ if(e.closest('div, ul, li')) {{ e.click(); return true; }} }}
                            return false;
                        }}''', dest)
                        
                        if not dest_found:
                            raise Exception(f"Destination {dest} dropdown item not found.")
                                
                        page.wait_for_timeout(1500)
                        
                        # --- DATE PICKER ---
                        page.get_by_placeholder(re.compile(r"Departure date", re.I)).click(force=True)
                        page.wait_for_timeout(1500)
                        
                        target_month_year = future_date_obj.strftime("%B %Y")
                        target_day = str(int(future_date_obj.strftime("%d")))
                        
                        for _ in range(5):
                            if page.get_by_text(target_month_year, exact=True).is_visible():
                                break
                            page.evaluate('''() => {
                                let btns = Array.from(document.querySelectorAll('button, svg'));
                                let nextBtn = btns.find(b => b.className && typeof b.className === 'string' && b.className.toLowerCase().includes('next') || (b.getAttribute('aria-label') || '').toLowerCase().includes('next'));
                                if (nextBtn) { let parent = nextBtn.closest('button'); if(parent) parent.click(); else nextBtn.click(); }
                            }''')
                            page.wait_for_timeout(800)
                        
                        js_click_logic = f"""
                        () => {{
                            let targetDay = '{target_day}';
                            let targetMonthYear = '{target_month_year}';
                            let monthHeaders = Array.from(document.querySelectorAll('*')).filter(el => el.textContent.trim() === targetMonthYear);
                            for (let header of monthHeaders) {{
                                let container = header.parentElement;
                                for (let i = 0; i < 6; i++) {{
                                    if (container) {{
                                        let leafNodes = Array.from(container.querySelectorAll('*')).filter(el => el.textContent.trim() === targetDay && el.children.length === 0);
                                        if (leafNodes.length > 0) {{
                                            let target = leafNodes[0];
                                            target.click();
                                            target.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
                                            return true;
                                        }}
                                        let cells = container.querySelectorAll('div, button, td');
                                        for (let cell of cells) {{
                                            if (cell.innerText) {{
                                                let lines = cell.innerText.trim().split('\\n');
                                                if (lines.length > 0 && lines[0].trim() === targetDay) {{
                                                    cell.click();
                                                    cell.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
                                                    return true;
                                                }}
                                            }}
                                        }}
                                    }}
                                    if (container) container = container.parentElement;
                                }}
                            }}
                            return false;
                        }}
                        """
                        page.evaluate(js_click_logic)
                        page.wait_for_timeout(1000)
                        
                        page.get_by_text("Search Flights").first.click(force=True)
                        
                        # --- RESULTS RENDERING WAIT ---
                        flights_loaded = False
                        for _ in range(30):
                            try:
                                body_text = page.locator("body").inner_text()
                                if "no flights" in body_text.lower() or "sold out" in body_text.lower():
                                    with sqlite3.connect('airfare_index.db') as conn:
                                        conn.execute('''
                                            INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                            VALUES (?, ?, ?, NULL, NULL, NULL, ?, NULL, NULL)
                                        ''', ("Akasa Air", route, window, "Akasa Direct"))
                                        conn.commit()
                                    print(f"ℹ️ Akasa officially returned no flights for T+{window}. Logging NULL.")
                                    flights_loaded = "EMPTY"
                                    break
                                
                                if body_text.count("₹") > 4 or body_text.count("Rs") > 4:
                                    flights_loaded = True
                                    break
                            except Exception:
                                pass
                            page.wait_for_timeout(1000)
                            
                        if not flights_loaded:
                            raise Exception("Flight results failed to render.")
                            
                        if flights_loaded == "EMPTY":
                            break
                        
                        # --- EXPLICIT ARIA-LABEL & SPAN EXTRACTION ---
                        valid_flights = page.evaluate(f"""() => {{
                            let records = [];
                            // Perfectly isolate the flight cards natively
                            let cards = document.querySelectorAll('div[aria-label="flight card"]');
                            
                            // Fallback just in case UI labels change slightly
                            if (cards.length === 0) {{
                                let allDivs = document.querySelectorAll('div');
                                let potentialCards = Array.from(allDivs).filter(d => {{
                                    let t = d.innerText || "";
                                    return /QP\\s*\\d{{3,4}}/i.test(t) && (t.includes('₹') || t.includes('Rs'));
                                }});
                                cards = potentialCards.filter(card => {{
                                    let childDivs = Array.from(card.querySelectorAll('div'));
                                    return !childDivs.some(child => potentialCards.includes(child));
                                }});
                            }}

                            cards.forEach(card => {{
                                let text = card.innerText || "";
                                let lowerT = text.toLowerCase();
                                
                                // 1. Strict Stoplist for Secondary Airports
                                if (lowerT.includes('navi mumbai') || lowerT.includes('ghaziabad') || 
                                    lowerT.includes('hindon') || lowerT.includes('noida') || 
                                    lowerT.includes('(nmi)') || lowerT.includes('(hdo)')) {{
                                    return;
                                }}

                                // 2. Native DOM Exact Routing Check (Akasa isolates IATA to SPANs)
                                let spans = Array.from(card.querySelectorAll('span'));
                                let hasOrig = spans.some(s => (s.innerText || "").trim().toUpperCase() === '{origin}');
                                let hasDest = spans.some(s => (s.innerText || "").trim().toUpperCase() === '{dest}');
                                
                                if (!hasOrig || !hasDest) return;

                                // 3. Extract Flight Number
                                let flightMatch = text.match(/QP\\s*(\\d{{3,4}})/i);
                                let flightNo = flightMatch ? ("QP-" + flightMatch[1]) : "";

                                // 4. Extract Departure Time
                                let times = text.match(/\\b(\\d{{2}}:\\d{{2}})\\b/g) || [];
                                let depTime = times.length > 0 ? times[0] : "";

                                // 5. Extract Prices
                                let priceMatches = text.match(/[₹|Rs]\\s*([\\d,]+)/g) || [];
                                let cleanPrices = priceMatches.map(p => parseInt(p.replace(/[^0-9]/g, ''))).filter(p => p > 1500 && p < 75000);

                                if (flightNo && cleanPrices.length > 0) {{
                                    records.push({{
                                        flight_no: flightNo,
                                        departure_time: depTime,
                                        fare: Math.min(...cleanPrices)
                                    }});
                                }}
                            }});

                            // 6. Deduplicate
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
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', [(
                                    "Akasa Air", 
                                    route, 
                                    window, 
                                    round(f['fare'] * 0.85, 2), 
                                    round(f['fare'] * 0.15, 2), 
                                    f['fare'], 
                                    "Akasa Direct", 
                                    f['departure_time'], 
                                    f['flight_no']
                                ) for f in valid_flights])
                                conn.commit()
                            print(f"✅ Saved {len(valid_flights)} direct records (Attempt {attempt}).")
                            break
                        else:
                            raise Exception("Zero valid flights extracted from card texts.")
                                        
                    except Exception as e:
                        print(f"⚠️ Akasa Attempt {attempt} failed: {e}")
                        if attempt == 1:
                            time.sleep(4)
                    
                time.sleep(2)

        context.close()
        print("\n🎉 Akasa Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_akasa_scraper()