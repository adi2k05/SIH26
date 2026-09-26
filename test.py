from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import time

def run_emt_multi_test():
    test_routes = ["DEL-BOM", "BOM-BLR"]
    test_windows = [1, 7]
    
    city_map = {
        "DEL": "Delhi", "BOM": "Mumbai", "BLR": "Bengaluru", 
        "HYD": "Hyderabad", "CCU": "Kolkata", "GOI": "Goa", 
        "MAA": "Chennai", "AMD": "Ahmedabad"
    }

    print(f"Launching EaseMyTrip Multi-Test Scraper ({len(test_routes)} Routes | {len(test_windows)} Windows)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        
        for route in test_routes:
            origin, dest = route.split("-")
            print(f"\n==================================================")
            print(f"🛫 STARTING ROUTE: {route}")
            print(f"==================================================")
            
            for window in test_windows:
                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d/%m/%Y")
                
                print(f"\n--- EaseMyTrip Test: {route} | T+{window} Days ({date_str}) ---")
                
                page = context.new_page()
                try:
                    url = f"https://flight.easemytrip.com/FlightList/Index?srch={origin}-{city_map[origin]}-India|{dest}-{city_map[dest]}-India|{date_str}&px=1-0-0&cbn=0&ar=undefined&isSplit=false&isOneway=true&isFreeFlight=false"
                    
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_selector('.main-bo-lis, .fltResult, div[id^="divFlightResult"], .flight-card', timeout=30000)
                    
                    print("Page loaded. Scrolling to populate all lazy-rendered flight cards...")
                    for _ in range(6):
                        page.evaluate("window.scrollBy(0, 1000);")
                        page.wait_for_timeout(1000)

                    js_extract = """() => {
                        let records = [];
                        let cards = document.querySelectorAll('.main-bo-lis, .fltResult, div[id^="divFlightResult"], .flight-card');
                        
                        cards.forEach(card => {
                            let cardText = card.innerText || "";
                            let lowerText = cardText.toLowerCase();
                            
                            // STRICT NON-STOP FILTER
                            let isNonStop = lowerText.includes('non-stop') || lowerText.includes('non stop') || lowerText.includes('0 stop') || lowerText.includes('nonstop');
                            if (!isNonStop) return;

                            // Extract Airline
                            let airlineEl = card.querySelector('.tx-thme, .air-line-name, span.txt-r4, .airline-name');
                            let rawAirline = airlineEl ? airlineEl.innerText.trim() : "Unknown Airline";
                            let actualAirline = rawAirline.replace(/Operated by|Partner/gi, '').trim();
                            if (!actualAirline) actualAirline = "EaseMyTrip Partner";

                            // Extract Price
                            let priceEl = card.querySelector('.txt-r6, .txt-r6-n, .price');
                            let cleanNum = 0;
                            if (priceEl && priceEl.innerText) {
                                cleanNum = parseInt(priceEl.innerText.replace(/[^0-9]/g, ''));
                            } else {
                                let pMatch = cardText.match(/[₹|Rs]\\s*([\\d,]+)/);
                                if (pMatch) cleanNum = parseInt(pMatch[1].replace(/,/g, ''));
                            }
                            if (isNaN(cleanNum) || cleanNum < 1500) return;

                            // Extract Flight Number
                            let flightEl = card.querySelector('.txt-r5');
                            let flightNo = "Unknown";
                            if (flightEl && flightEl.innerText) {
                                flightNo = flightEl.innerText.replace(/\\s+/g, ' ').replace('\\n', '').trim();
                            } else {
                                let fMatch = cardText.match(/([A-Z0-9]{2})[-\\s]?(\\d{3,4})/i);
                                if (fMatch) flightNo = fMatch[1].toUpperCase() + "-" + fMatch[2];
                            }

                            // Extract Departure Time
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
                        
                        // Deduplicate
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

                    # --- BULLETPROOF PYTHON ROUTE CHECK ---
                    verified_flights = []
                    
                    if extracted_flights:
                        # Prepare lower-case validation keys
                        origin_code = origin.lower()
                        dest_code = dest.lower()
                        origin_city = city_map[origin].lower()
                        dest_city = city_map[dest].lower()
                        
                        # List of alternate airports to aggressively reject
                        bad_airports = ["navi mumbai", "(nmi)", "nmi", "ghaziabad", "hindon", "(hdo)", "hdo"]

                        for f in extracted_flights:
                            # Force everything to lowercase for safe matching
                            raw_txt = f.get("card_text", "").lower()
                            
                            # 1. Reject if ANY bad airport keyword is found in the card text
                            if any(bad in raw_txt for bad in bad_airports):
                                continue

                            # 2. Verify that Origin (Code OR City) is present
                            has_origin = origin_code in raw_txt or origin_city in raw_txt
                            # 3. Verify that Destination (Code OR City) is present
                            has_dest = dest_code in raw_txt or dest_city in raw_txt

                            if has_origin and has_dest:
                                verified_flights.append(f)

                    if verified_flights:
                        print(f"✅ Extracted {len(verified_flights)} strictly verified Non-Stop flights (filtered out {len(extracted_flights) - len(verified_flights)} alternate routes).")
                        for idx, f in enumerate(verified_flights):
                            base = round(f['fare'] * 0.85, 2)
                            tax = round(f['fare'] * 0.15, 2)
                            print(f" {idx+1:2d}. [{f['airline']}] Flight: {f['flight_no']} | Dept: {f['departure_time']} | Base: ₹{base} | Tax: ₹{tax} | Total: ₹{f['fare']}")
                    else:
                        print(f"⚠️ Zero valid non-stop flights matched criteria (Raw JS Extracted: {len(extracted_flights) if extracted_flights else 0}).")

                except Exception as e:
                    print(f"⚠️ Test run failed: {e}")
                finally:
                    page.close()
                    time.sleep(3) 

            print(f"⏳ Route {route} complete. Cooling down before next route...")
            time.sleep(6)
            
        browser.close()

if __name__ == "__main__":
    run_emt_multi_test()