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

    print(f"Launching Yatra Scraper for {len(top_20_routes)} routes...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        
        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                future_date = (datetime.now() + timedelta(days=window)).strftime("%d/%m/%Y")
                search_url = f"https://flight.yatra.com/air-search-ui/dom2/trigger?type=O&viewName=normal&flexi=0&noOfSegments=1&origin={origin}&originCountry=IN&destination={dest}&destinationCountry=IN&flight_depart_date={future_date}&ADT=1&CHD=0&INF=0&class=Economy"
                
                print(f"\n--- Yatra Scraping: {route} | T+{window} Days ({future_date}) ---")
                
                try:
                    page.goto(search_url, timeout=60000)
                    page.wait_for_timeout(25000) 
                    
                    page.evaluate("window.scrollBy(0, 1000)")
                    page.wait_for_timeout(3000)
                    
                    page_text = page.locator("body").inner_text()
                    lines = [line.strip() for line in page_text.split('\n') if line.strip()]
                    airlines = ["IndiGo", "Air India", "SpiceJet", "Akasa Air", "Air India Express"]
                    
                    conn = sqlite3.connect('airfare_index.db')
                    cursor = conn.cursor()
                    inserted_count = 0
                    
                    for i, line in enumerate(lines):
                        if any(airline in line for airline in airlines):
                            matched_airline = next(airline for airline in airlines if airline in line)
                            
                            for j in range(1, 15):
                                if i + j < len(lines):
                                    clean_text = lines[i+j].replace("₹", "").replace("Rs", "").replace(",", "").strip()
                                    
                                    if re.match(r'^\d{4,5}$', clean_text):
                                        total_fare = int(clean_text)
                                        
                                        if 1500 < total_fare < 75000:
                                            base_fare = round(total_fare * 0.85, 2)
                                            taxes_fees = round(total_fare * 0.15, 2)
                                            
                                            cursor.execute('''
                                                INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source)
                                                VALUES (?, ?, ?, ?, ?, ?, 'Yatra')
                                            ''', (matched_airline, route, window, base_fare, taxes_fees, total_fare))
                                            
                                            inserted_count += 1
                                            break 
                    
                    conn.commit()
                    conn.close()
                    print(f"✅ Saved {inserted_count} records")
                                    
                except Exception as e:
                    print(f"Extraction error for {route} T+{window}:", e)
                
                time.sleep(5)

        browser.close()
        print("\nYatra Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_yatra_scraper()