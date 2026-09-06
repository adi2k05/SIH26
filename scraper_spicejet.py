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

def run_spicejet_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    print("Launching SpiceJet Multi-Route Scraper (Resilient Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        
        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                if is_already_scraped(route, window, "SpiceJet Direct"):
                    print(f"⏩ SpiceJet: {route} | T+{window} already collected today. Skipping.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%Y-%m-%d")
                print(f"\n--- SpiceJet Scraping: {route} | T+{window} Days ({date_str}) ---")
                
                for attempt in range(1, 3):
                    page = context.new_page() 
                    try:
                        url = f"https://www.spicejet.com/search?from={origin}&to={dest}&tripType=1&departure={date_str}&adult=1&child=0&srCitizen=0&infant=0&currency=INR"
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        
                        flights_loaded = False
                        no_flights_scheduled = False
                        
                        for _ in range(30):
                            try:
                                body_text = page.locator("body").inner_text()
                                
                                # THE FIX: Match the exact text from the SpiceJet UI
                                if "Unfortunately, there are no flights available" in body_text or "no flights available" in body_text.lower():
                                    no_flights_scheduled = True
                                    break

                                if "Flight Details" in body_text or "SpiceMax" in body_text or body_text.count("₹") > 3:
                                    flights_loaded = True
                                    break
                            except Exception as e:
                                if "Execution context was destroyed" in str(e):
                                    page.wait_for_timeout(1000)
                                    continue
                            page.wait_for_timeout(1000)
                        
                        if no_flights_scheduled:
                            print(f"ℹ️ SpiceJet does not operate flights on {route} for T+{window}.")
                            page.close()
                            break

                        if not flights_loaded:
                            raise Exception("Flight matrix timed out.")
                            
                        page.wait_for_timeout(2500)
                        try:
                            page.evaluate("window.scrollBy(0, 1500)")
                        except Exception:
                            pass
                        page.wait_for_timeout(1500)
                        
                        lines = [l.strip() for l in page.locator("body").inner_text().split('\n') if l.strip()]
                        fares = [int(re.sub(r'[^\d]', '', l)) for l in lines if ('₹' in l or 'Rs' in l) and re.sub(r'[^\d]', '', l)]
                        valid_fares = [f for f in fares if 1500 < f < 75000]
                        
                        if valid_fares:
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                ''', [("SpiceJet", route, window, round(f * 0.85, 2), round(f * 0.15, 2), f, "SpiceJet Direct") for f in valid_fares])
                                conn.commit()
                            print(f"✅ Saved {len(valid_fares)} direct records (Attempt {attempt}).")
                            page.close()
                            break
                        else:
                            raise Exception("No fare values captured.")
                                        
                    except Exception as e:
                        print(f"⚠️ SpiceJet Attempt {attempt} failed: {e}")
                        page.close()
                        if attempt == 1:
                            time.sleep(5)
                    
                time.sleep(2)

        browser.close()
        print("\nSpiceJet Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_spicejet_scraper()