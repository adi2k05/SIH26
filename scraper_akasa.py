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
    # Akasa Air operates at Manohar International (GOX), not Dabolim (GOI).
    unsupported_akasa_routes = [
        "DEL-GOI", "BOM-GOI"
    ]
    
    print("Launching Akasa Air Scraper (Bulletproof Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            # --- BYPASS NON-OPERATED ROUTES INSTANTLY ---
            if route in unsupported_akasa_routes:
                print(f"ℹ️ {route} is unsupported by Akasa (uses GOX instead of GOI). Skipping permanently.")
                for window in advance_windows:
                    if not is_already_scraped(route, window, "Akasa Direct"):
                        with sqlite3.connect('airfare_index.db') as conn:
                            conn.execute('''
                                INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time)
                                VALUES (?, ?, ?, NULL, NULL, NULL, ?, NULL)
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
                    context = browser.new_context(viewport={"width": 1920, "height": 1080})
                    page = context.new_page() 
                    
                    try:
                        page.goto("https://www.akasaair.com/", wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(3500) 
                        
                        loc_from = page.locator("#From")
                        loc_from.click(force=True)
                        page.wait_for_timeout(500)
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.type(origin, delay=200)
                        page.wait_for_timeout(3000)
                        
                        origin_found = page.evaluate(f'''(iata) => {{
                            let els = Array.from(document.querySelectorAll('*')).filter(e => e.textContent.trim() === iata && e.children.length === 0);
                            for(let e of els) {{ if(e.closest('div, ul, li')) {{ e.click(); return true; }} }}
                            return false;
                        }}''', origin)
                        
                        if not origin_found:
                            raise Exception(f"Origin {origin} not selectable in dropdown. Retrying...")
                        
                        page.wait_for_timeout(2500)
                        
                        loc_to = page.locator("#To")
                        loc_to.click(force=True)
                        page.wait_for_timeout(500)
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.type(dest, delay=200)
                        page.wait_for_timeout(3000)
                        
                        dest_found = page.evaluate(f'''(iata) => {{
                            let els = Array.from(document.querySelectorAll('*')).filter(e => e.textContent.trim() === iata && e.children.length === 0);
                            for(let e of els) {{ if(e.closest('div, ul, li')) {{ e.click(); return true; }} }}
                            return false;
                        }}''', dest)
                        
                        if not dest_found:
                            # --- CRITICAL FIX: Treat as UI Lag ---
                            # Do NOT insert NULL. Throw exception to retry the attempt.
                            raise Exception(f"Destination {dest} not selectable in dropdown. Retrying...")
                                
                        page.wait_for_timeout(1500)
                        
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
                        
                        flights_loaded = False
                        for _ in range(30):
                            try:
                                body_text = page.locator("body").inner_text()
                                # Log NULL safely only if the results page explicitly states no flights
                                if "no flights" in body_text.lower() or "sold out" in body_text.lower():
                                    with sqlite3.connect('airfare_index.db') as conn:
                                        conn.execute('''
                                            INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time)
                                            VALUES (?, ?, ?, NULL, NULL, NULL, ?, NULL)
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
                            context.close()
                            break
                        
                        lines = [l.strip() for l in page.locator("body").inner_text().split('\n') if l.strip()]
                        fares = [int(re.sub(r'[^\d]', '', l)) for l in lines if ('₹' in l or 'Rs' in l) and re.sub(r'[^\d]', '', l)]
                        valid_fares = [f for f in fares if 1500 < f < 75000]
                        
                        if valid_fares:
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                ''', [("Akasa Air", route, window, round(f * 0.85, 2), round(f * 0.15, 2), f, "Akasa Direct", f"T{idx+1}") for idx, f in enumerate(valid_fares)])
                                conn.commit()
                            print(f"✅ Saved {len(valid_fares)} direct records (Attempt {attempt}).")
                            context.close()
                            break
                        else:
                            raise Exception("Zero fares extracted.")
                                        
                    except Exception as e:
                        print(f"⚠️ Akasa Attempt {attempt} failed: {e}")
                        context.close()
                        if attempt == 1:
                            time.sleep(5)
                    
                time.sleep(2)

        browser.close()
        print("\nAkasa Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_akasa_scraper()