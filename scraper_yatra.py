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
            AND date(datetime(timestamp, '+5 hours', '+30 minutes')) = date(datetime('now', '+5 hours', '+30 minutes'))
        """, (route, window, source))
        return c.fetchone()[0] > 0

def run_yatra_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    print("Launching Yatra Multi-Route Scraper (Resilient Retry Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
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
                            
                        page.wait_for_timeout(3000)
                        try:
                            page.evaluate("window.scrollBy(0, 1500)")
                        except Exception:
                            page.wait_for_timeout(2000)
                            page.evaluate("window.scrollBy(0, 1500)")
                            
                        page.wait_for_timeout(1500)
                        
                        lines = [l.strip() for l in page.locator("body").inner_text().split('\n') if l.strip()]
                        fares = [int(re.sub(r'[^\d]', '', l)) for l in lines if ('₹' in l or 'Rs' in l) and re.sub(r'[^\d]', '', l)]
                        valid_fares = [f for f in fares if 1500 < f < 75000]
                        
                        if valid_fares:
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                ''', [("Yatra Partner", route, window, round(f * 0.85, 2), round(f * 0.15, 2), f, "Yatra", f"T{idx+1}") for idx, f in enumerate(valid_fares)])  
                                conn.commit()
                            print(f"✅ Saved {len(valid_fares)} records (Attempt {attempt}).")
                            page.close()
                            break
                        else:
                            raise Exception("Zero valid fare numbers parsed.")
                                        
                    except Exception as e:
                        print(f"⚠️ Yatra Attempt {attempt} failed: {e}")
                        page.close()
                        if attempt == 1:
                            time.sleep(5)
                    
                time.sleep(2)

        browser.close()
        print("\nYatra Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_yatra_scraper()