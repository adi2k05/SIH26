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
        try:
            c.execute("""
                SELECT COUNT(*) FROM raw_fares 
                WHERE route = ? AND advance_window_days = ? AND ota_source = ? 
                AND date(timestamp) = date(datetime('now', '+5 hours', '+30 minutes'))
            """, (route, window, source))
            return c.fetchone()[0] > 0
        except sqlite3.OperationalError:
            return False

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

    print("Launching EaseMyTrip Multi-Route Scraper (Resilient Retry Mode & Strict Route Checking)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            # Map codes to lowercase city names for Python strict validation
            origin_code, dest_code = origin.lower(), dest.lower()
            origin_city, dest_city = city_map[origin].lower(), city_map[dest].lower()
            
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
                        page.wait_for_selector(".main-bo-lis, .fltResult, div[id^='divFlightResult'], .flight-card", timeout=30000)
                        
                        # A small scroll to ensure lazy-loaded elements populate
                        for _ in range(5):
                            page.evaluate("window.scrollBy(0, 1000);")
                            page.wait_for_timeout(1000)

                        # --- UPDATED JS EXTRACTION: Airline, Fare, Flight No, Time & Raw Text ---
                        js_extract = """() => {
                            let records = [];
                            let cards = document.querySelectorAll('.main-bo-lis, .fltResult, div[id^="divFlightResult"], .flight-card');
                            
                            cards.forEach(card => {
                                let cardText = card.innerText || "";
                                let lowerText = cardText.toLowerCase();
                                
                                // STRICT NON-STOP FILTER
                                let isNonStop = lowerText.includes('non-stop') || lowerText.includes('non stop') || lowerText.includes('0 stop') || lowerText.includes('nonstop');
                                if (!isNonStop) return;

                                // 1. Extract Airline
                                let airlineEl = card.querySelector('.tx-thme, .air-line-name, span.txt-r4, .airline-name');
                                let rawAirline = airlineEl ? airlineEl.innerText.trim() : "Unknown Airline";
                                let actualAirline = rawAirline.replace(/Operated by|Partner/gi, '').trim();
                                if (!actualAirline) actualAirline = "EaseMyTrip Partner";

                                // 2. Extract Price
                                let priceEl = card.querySelector('.txt-r6, .txt-r6-n, .price');
                                let cleanNum = 0;
                                if (priceEl && priceEl.innerText) {
                                    cleanNum = parseInt(priceEl.innerText.replace(/[^0-9]/g, ''));
                                } else {
                                    let pMatch = cardText.match(/[₹|Rs]\\s*([\\d,]+)/);
                                    if (pMatch) cleanNum = parseInt(pMatch[1].replace(/,/g, ''));
                                }
                                if (isNaN(cleanNum) || cleanNum < 1500) return;

                                // 3. Extract Flight Number
                                let flightEl = card.querySelector('.txt-r5');
                                let flightNo = "Unknown";
                                if (flightEl && flightEl.innerText) {
                                    flightNo = flightEl.innerText.replace(/\\s+/g, ' ').replace('\\n', '').trim();
                                } else {
                                    let fMatch = cardText.match(/([A-Z0-9]{2})[-\\s]?(\\d{3,4})/i);
                                    if (fMatch) flightNo = fMatch[1].toUpperCase() + "-" + fMatch[2];
                                }

                                // 4. Extract Departure Time
                                let depTime = "Unknown";
                                let timeMatches = cardText.match(/\\b(\\d{2}:\\d{2})\\b/g);
                                if (timeMatches && timeMatches.length > 0) {
                                    depTime = timeMatches[0];
                                }

                                records.push({
                                    airline: actualAirline,
                                    flight_no: flightNo,
                                    departure_time: depTime,
                                    fare: cleanNum,
                                    card_text: cardText 
                                });
                            });
                            
                            // Deduplicate based on flight number and departure time
                            let unique = {};
                            records.forEach(f => {
                                let key = f.flight_no + "_" + f.departure_time;
                                if (!unique[key] || f.fare < unique[key].fare) {
                                    unique[key] = f;
                                }
                            });
                            return Object.values(unique);
                        }"""
                        
                        extracted_flights = page.evaluate(js_extract)

                        # --- PYTHON POST-SCRAPE FILTERING (Strict City Verification) ---
                        valid_flights = []
                        bad_airports = ["navi mumbai", "(nmi)", "nmi", "ghaziabad", "hindon", "(hdo)", "hdo"]

                        if extracted_flights:
                            for f in extracted_flights:
                                raw_txt = f.get("card_text", "").lower()
                                
                                # 1. Reject if alternate airport detected
                                if any(bad in raw_txt for bad in bad_airports):
                                    continue

                                # 2. Verify Origin & Destination
                                has_origin = origin_code in raw_txt or origin_city in raw_txt
                                has_dest = dest_code in raw_txt or dest_city in raw_txt

                                # 3. Fare threshold check
                                if has_origin and has_dest and 1500 < f['fare'] < 75000:
                                    valid_flights.append(f)

                        # --- DATABASE INSERTION ---
                        if valid_flights:
                            with sqlite3.connect('airfare_index.db') as conn:
                                # Create table securely if missing DB columns (flight_no)
                                conn.execute("""
                                    CREATE TABLE IF NOT EXISTS raw_fares (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                        airline TEXT, route TEXT, advance_window_days INTEGER,
                                        base_fare REAL, taxes_fees REAL, total_fare REAL,
                                        ota_source TEXT, departure_time TEXT, flight_no TEXT
                                    )
                                """)
                                
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', [(
                                    flight['airline'], 
                                    route, 
                                    window, 
                                    round(flight['fare'] * 0.85, 2), 
                                    round(flight['fare'] * 0.15, 2), 
                                    flight['fare'], 
                                    "EaseMyTrip", 
                                    flight['departure_time'], 
                                    flight['flight_no'] 
                                ) for flight in valid_flights])
                                conn.commit()
                                
                            print(f"✅ Saved {len(valid_flights)} records (Attempt {attempt}).")
                            page.close()
                            break
                        else:
                            raise Exception("Zero valid strictly filtered non-stop flights extracted.")

                    except Exception as e:
                        print(f"⚠️ EMT Attempt {attempt} failed: {e}")
                        page.close()
                        if attempt == 1:
                            time.sleep(5)
                
                time.sleep(2)

        browser.close()
        print("\n🎉 EaseMyTrip Scraping Complete!")

if __name__ == "__main__":
    run_emt_scraper()