from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import sqlite3
import re
import time

def run_spicejet_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    print("Launching SpiceJet Multi-Route Scraper (Dynamic Polling Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        
        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%Y-%m-%d")

                print(f"\n--- SpiceJet Scraping: {route} | T+{window} Days ({date_str}) ---")
                
                page = context.new_page() 
                
                try:
                    url = f"https://www.spicejet.com/search?from={origin}&to={dest}&tripType=1&departure={date_str}&adult=1&child=0&srCitizen=0&infant=0&currency=INR"
                    page.goto(url, timeout=60000)
                    
                    flights_loaded = False
                    
                    # Dynamic Polling Loop to survive React State Hydration reloads
                    for _ in range(40):
                        try:
                            body_text = page.locator("body").inner_text()
                            if "₹" in body_text or "Rs" in body_text:
                                # Ensure we aren't just seeing the footer currency selector
                                if "Flight Details" in body_text or "SpiceMax" in body_text or len(re.findall(r'₹', body_text)) > 3:
                                    flights_loaded = True
                                    break
                        except Exception as e:
                            if "Execution context was destroyed" in str(e) or "Target page" in str(e) or "detached" in str(e):
                                page.wait_for_timeout(1500)
                                continue
                        
                        page.wait_for_timeout(1000)
                    
                    if not flights_loaded:
                        print("⚠️ Timeout: Flights did not render.")
                        continue
                        
                    # Mandatory DOM stabilization before JS execution
                    page.wait_for_timeout(3000)
                    
                    try:
                        page.evaluate("window.scrollBy(0, 1500)")
                    except Exception:
                        page.wait_for_timeout(2000)
                        
                    page.wait_for_timeout(2000)
                    
                    # Extract & Clean Data
                    lines = [line.strip() for line in page.locator("body").inner_text().split('\n') if line.strip()]
                    
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
                            ''', [("SpiceJet", route, window, round(f * 0.85, 2), round(f * 0.15, 2), f, "SpiceJet Direct") for f in valid_fares])
                            conn.commit()
                        print(f"✅ Saved {len(valid_fares)} direct records.")
                    else:
                        print("⚠️ No valid fares found.")
                                    
                except Exception as e:
                    print(f"❌ Extraction error: {e}")
                
                finally:
                    page.close()
                
                time.sleep(2)

        browser.close()
        print("\nSpiceJet Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_spicejet_scraper()