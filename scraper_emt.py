from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import sqlite3
import re
import time

def run_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    airport_map = {
        "DEL": "Delhi", "BOM": "Mumbai", "BLR": "Bangalore", 
        "HYD": "Hyderabad", "CCU": "Kolkata", "GOI": "Goa", 
        "MAA": "Chennai", "AMD": "Ahmedabad"
    }
    
    print(f"Launching EaseMyTrip Scraper for {len(top_20_routes)} routes...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                future_date = (datetime.now() + timedelta(days=window)).strftime("%d/%m/%Y")
                url = f"https://flight.easemytrip.com/FlightList/Index?srch={origin}-{airport_map[origin]}-India|{dest}-{airport_map[dest]}-India|{future_date}&px=1-0-0&cbn=0&ar=undefined&isSplit=false&isOneway=true&isFreeFlight=false"

                print(f"\n--- EaseMyTrip Scraping: {route} | T+{window} Days ({future_date}) ---")
                
                try:
                    page.goto(url, timeout=60000)
                    
                    print("Waiting dynamically for EaseMyTrip flights to render...")
                    for attempt in range(15):
                        current_text = page.locator("body").inner_text()
                        if "₹" in current_text or "Rs" in current_text:
                            print(f"-> Flights loaded in ~{attempt + 1} seconds!")
                            break
                        page.wait_for_timeout(1000)
                    
                    page.evaluate("window.scrollBy(0, 1000)")
                    page.wait_for_timeout(2000) 
                    
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
                                    clean_text = lines[i+j].replace("₹", "").replace("Rs", "").strip()
                                    
                                    if re.match(r'^\d{1,2},\d{3}$', clean_text) or re.match(r'^\d{4,5}$', clean_text):
                                        total_fare = int(clean_text.replace(',', ''))
                                        
                                        if total_fare > 1500:
                                            base_fare = round(total_fare * 0.85, 2)
                                            taxes_fees = round(total_fare * 0.15, 2)
                                            
                                            cursor.execute('''
                                                INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source)
                                                VALUES (?, ?, ?, ?, ?, ?, 'EaseMyTrip')
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
        print("\nEaseMyTrip Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_scraper()