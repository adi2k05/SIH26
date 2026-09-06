from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import sqlite3
import re
import time

def run_yatra_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    print("Launching Yatra Multi-Route Scraper (Strict Verification Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d/%m/%Y")
                
                print(f"\n--- Yatra Scraping: {route} | T+{window} Days ({date_str}) ---")
                
                page = context.new_page() 
                
                try:
                    url = f"https://flight.yatra.com/air-search-ui/dom2/trigger?type=O&viewName=normal&flexi=0&noOfSegments=1&origin={origin}&originCountry=IN&destination={dest}&destinationCountry=IN&flight_depart_date={date_str}&ADT=1&CHD=0&INF=0&class=Economy&source=fresco-home"
                    page.goto(url, timeout=60000)
                    
                    flights_loaded = False
                    for _ in range(40): 
                        try:
                            body_text = page.locator("body").inner_text()
                            if "Akamai" in body_text or "waiting" in body_text.lower():
                                page.wait_for_timeout(1000)
                                continue
                                
                            # THE FIX: Demand at least 5 prices on screen to prove the flight list has loaded, bypassing header symbols
                            if body_text.count("₹") > 4 or body_text.count("Rs") > 4:
                                flights_loaded = True
                                break
                        except Exception:
                            page.wait_for_timeout(1000)
                            continue
                            
                        page.wait_for_timeout(1000)
                    
                    if not flights_loaded:
                        print("⚠️ Timeout: Flights did not render after Akamai redirect.")
                        continue
                        
                    page.wait_for_timeout(3500)
                    
                    try:
                        page.evaluate("window.scrollBy(0, 1500)")
                    except Exception:
                        page.wait_for_timeout(4000)
                        page.evaluate("window.scrollBy(0, 1500)")
                        
                    page.wait_for_timeout(2000)
                    
                    # Extract & Clean Data
                    page_text = page.locator("body").inner_text()
                    lines = [line.strip() for line in page_text.split('\n') if line.strip()]
                    
                    fares = []
                    for line in lines:
                        if '₹' in line or 'Rs' in line:
                            clean_text = re.sub(r'[^\d]', '', line)
                            if clean_text:
                                fares.append(int(clean_text))
                                
                    valid_fares = [f for f in fares if 1500 < f < 75000]
                    
                    # Bulk Insert
                    if valid_fares:
                        with sqlite3.connect('airfare_index.db') as conn:
                            conn.executemany('''
                                INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', [("Yatra", route, window, round(f * 0.85, 2), round(f * 0.15, 2), f, "Yatra") for f in valid_fares])
                            conn.commit()
                        print(f"✅ Saved {len(valid_fares)} direct records.")
                    else:
                        print("⚠️ No valid fares found on page.")
                                    
                except Exception as e:
                    print(f"❌ Extraction error: {e}")
                
                finally:
                    page.close()
                
                time.sleep(2)

        browser.close()

if __name__ == "__main__":
    run_yatra_scraper()