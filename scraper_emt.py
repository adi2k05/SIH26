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
                
                for attempt in range(1, 3):
                    page = context.new_page()
                    try:
                        url = f"https://flight.easemytrip.com/FlightList/Index?srch={origin}-{city_map[origin]}-India|{dest}-{city_map[dest]}-India|{date_str}&px=1-0-0&cbn=0&ar=undefined&isSplit=false&isOneway=true&isFreeFlight=false"
                        
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        
                        # Wait specifically for the flight list container to render
                        page.wait_for_selector(".fltResult, div[id^='divFlightResult'], .flight-card", timeout=30000)
                        
                        # A small scroll to ensure lazy-loaded elements populate
                        page.evaluate("window.scrollBy(0, 1500)")
                        page.wait_for_timeout(2000)

                        # --- UPDATED JS EXTRACTION: Airline & Fare ---
                        extracted_flights = page.evaluate("""() => {
                            let flights = [];
                            let cards = document.querySelectorAll('.fltResult, div[id^="divFlightResult"], .flight-card');
                            
                            cards.forEach(card => {
                                // 1. Extract Airline
                                let airlineEl = card.querySelector('.tx-thme, .air-line-name, span.txt-r4, .airline-name');
                                let rawAirline = airlineEl ? airlineEl.innerText.trim() : "Unknown Airline";
                                // Clean up generic partner tags from the name
                                let actualAirline = rawAirline.replace(/Operated by|Partner/gi, '').trim();
                                if (!actualAirline) actualAirline = "EaseMyTrip Partner";

                                // 2. Extract Price
                                let priceEl = card.querySelector('.txt-r6, .txt-r6-n, .price');
                                if (priceEl && priceEl.innerText) {
                                    let cleanNum = parseInt(priceEl.innerText.replace(/[^0-9]/g, ''));
                                    if (!isNaN(cleanNum)) {
                                        flights.push({
                                            airline: actualAirline,
                                            fare: cleanNum
                                        });
                                    }
                                }
                            });
                            return flights;
                        }""")

                        # Filter out invalid fares
                        valid_flights = [f for f in extracted_flights if 1500 < f['fare'] < 75000]

                        if valid_flights:
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                ''', [(
                                    flight['airline'], 
                                    route, 
                                    window, 
                                    round(flight['fare'] * 0.85, 2), 
                                    round(flight['fare'] * 0.15, 2), 
                                    flight['fare'], 
                                    "EaseMyTrip", 
                                    f"T{idx+1}" 
                                ) for idx, flight in enumerate(valid_flights)])
                                conn.commit()
                                
                            print(f"✅ Saved {len(valid_flights)} records (Attempt {attempt}).")
                            page.close()
                            break
                        else:
                            raise Exception("Zero valid flights extracted from DOM.")

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