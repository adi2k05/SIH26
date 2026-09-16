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

def run_ixigo_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    print("Launching Ixigo Scraper (Bulletproof Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                if is_already_scraped(route, window, "Ixigo"):
                    print(f"⏩ Ixigo: {route} | T+{window} already collected today. Skipping.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d%m%Y")
                
                search_url = f"https://www.ixigo.com/search/result/flight?from={origin}&to={dest}&date={date_str}&adults=1&children=0&infants=0&class=e"
                
                print(f"\n--- Ixigo Scraping: {route} | T+{window} Days ---")
                
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
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time)
                                    VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?)
                                ''', ("Unknown", route, window, "Ixigo", "TBD"))
                                conn.commit()
                            context.close()
                            break 
                        
                        print("Scrolling to load all flights...")
                        seen_flights = set()
                        route_data = []
                        flight_idx = 1
                        
                        js_extractor = """
                        () => {
                            let results = [];
                            let allElements = Array.from(document.querySelectorAll('*'));
                            let flightNumberElements = allElements.filter(el => {
                                let text = el.textContent.trim();
                                return /^[A-Z0-9]{2}\\s?\\d{3,4}$/.test(text) && el.children.length === 0;
                            });
                            
                            flightNumberElements.forEach(fnEl => {
                                let parent = fnEl.parentElement;
                                let card = null;
                                for (let i = 0; i < 15; i++) {
                                    if (!parent) break;
                                    let text = parent.innerText || parent.textContent;
                                    if (text.includes('₹') && text.length > 50) {
                                        card = parent;
                                        break;
                                    }
                                    parent = parent.parentElement;
                                }
                                if (card) {
                                    results.push(card.innerText);
                                }
                            });
                            return results;
                        }
                        """
                        
                        scroll_attempts = 0
                        max_scrolls = 40
                        last_flight_count = 0
                        stagnant_scrolls = 0
                        
                        while scroll_attempts < max_scrolls:
                            card_texts = page.evaluate(js_extractor)
                            
                            for card_text in card_texts:
                                lines = [line.strip() for line in card_text.split('\n') if line.strip()]
                                
                                flight_number = None
                                airline = "Unknown"
                                total_fare = 0
                                
                                for i, line in enumerate(lines):
                                    if re.match(r'^[A-Z0-9]{2}\s?\d{3,4}$', line):
                                        flight_number = line.replace(" ", "")
                                        if i > 0:
                                            airline = lines[i-1]
                                    
                                    if "₹" in line:
                                        clean = line.replace("₹", "").replace(",", "").strip()
                                        if re.match(r'^\d{4,6}$', clean):
                                            total_fare = int(clean)
                                
                                if flight_number and total_fare > 1000:
                                    if flight_number not in seen_flights:
                                        seen_flights.add(flight_number)
                                        base_fare = round(total_fare * 0.85, 2)
                                        taxes_fees = round(total_fare * 0.15, 2)
                                        
                                        dept_time = f"T{flight_idx}"
                                        flight_idx += 1
                                        
                                        route_data.append((
                                            airline, route, window, 
                                            base_fare, taxes_fees, total_fare, "Ixigo", dept_time
                                        ))
                            
                            if len(seen_flights) == last_flight_count:
                                stagnant_scrolls += 1
                                if stagnant_scrolls >= 4:
                                    break 
                            else:
                                stagnant_scrolls = 0
                                
                            last_flight_count = len(seen_flights)
                            
                            # --- HARDWARE SCROLL FIX ---
                            # 1. Move the mouse to the center of the page (960, 540 is center of 1920x1080)
                            page.mouse.move(960, 540)
                            # 2. Simulate a physical mouse wheel spin downwards
                            page.mouse.wheel(0, 1200)
                            # 3. Add a PageDown keypress just in case the mouse misses the container
                            page.keyboard.press("PageDown")
                            
                            page.wait_for_timeout(2000)
                            scroll_attempts += 1
                        
                        if route_data:
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                ''', route_data)
                                conn.commit()
                            print(f"✅ Saved {len(route_data)} unique records (Attempt {attempt}).")
                            context.close()
                            break 
                        else:
                            raise Exception("Zero valid flights extracted.")
                                        
                    except Exception as e:
                        print(f"⚠️ Ixigo Attempt {attempt} failed: {e}")
                        context.close()
                        if attempt == 1:
                            time.sleep(5)
                    
                time.sleep(2)

        browser.close()
        print("\nIxigo Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_ixigo_scraper()