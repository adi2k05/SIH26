from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import sqlite3
import re
import time

def is_already_scraped(route, window, source):
    with sqlite3.connect('airfare_index.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM raw_fares 
            WHERE route = ? AND advance_window_days = ? AND ota_source = ? 
            AND date(timestamp) = date('now')
        """, (route, window, source))
        return c.fetchone()[0] > 0

def run_emt_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    city_map = {
        "DEL": "Delhi", "BOM": "Mumbai", "BLR": "Bengaluru", 
        "HYD": "Hyderabad", "CCU": "Kolkata", "GOI": "Goa", 
        "MAA": "Chennai", "AMD": "Ahmedabad"
    }

    print("Launching EaseMyTrip Multi-Route Scraper (Resilient Retry Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                if is_already_scraped(route, window, "EaseMyTrip"):
                    print(f"⏩ EMT: {route} | T+{window} already collected today. Skipping.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d/%m/%Y")
                print(f"\n--- EaseMyTrip Scraping: {route} | T+{window} Days ({date_str}) ---")
                
                # Up to 2 attempts per route-window
                for attempt in range(1, 3):
                    page = context.new_page()
                    try:
                        url = f"https://flight.easemytrip.com/FlightList/Index?srch={origin}-{city_map[origin]}-India|{dest}-{city_map[dest]}-India|{date_str}&px=1-0-0&cbn=0&ar=undefined&isSplit=false&isOneway=true&isFreeFlight=false"
                        
                        # FIX: Use domcontentloaded instead of full load to prevent socket closing
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        
                        # Wait for flight rows to anchor
                        flights_loaded = False
                        for _ in range(25):
                            body_text = page.locator("body").inner_text()
                            if body_text.count("₹") > 5 or body_text.count("Rs") > 5:
                                flights_loaded = True
                                break
                            page.wait_for_timeout(1000)
                            
                        if not flights_loaded:
                            raise Exception("Flight cards did not render in DOM.")

                        page.evaluate("window.scrollBy(0, 1500)")
                        page.wait_for_timeout(1500)

                        lines = [l.strip() for l in page.locator("body").inner_text().split('\n') if l.strip()]
                        fares = [int(re.sub(r'[^\d]', '', l)) for l in lines if ('₹' in l or 'Rs' in l) and re.sub(r'[^\d]', '', l)]
                        valid_fares = [f for f in fares if 1500 < f < 75000]

                        if valid_fares:
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                ''', [("EaseMyTrip Partner", route, window, round(f * 0.85, 2), round(f * 0.15, 2), f, "EaseMyTrip") for f in valid_fares])
                                conn.commit()
                            print(f"✅ Saved {len(valid_fares)} records (Attempt {attempt}).")
                            page.close()
                            break
                        else:
                            raise Exception("Zero valid fare numbers parsed.")

                    except Exception as e:
                        print(f"⚠️ EMT Attempt {attempt} failed: {e}")
                        page.close()
                        if attempt == 1:
                            time.sleep(5)
                
                time.sleep(2)

        browser.close()
        print("\nEaseMyTrip Scraping Complete!")

if __name__ == "__main__":
    run_emt_scraper()