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
            
            origin_name = city_map[origin].lower()
            dest_name = city_map[dest].lower()
            
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

                    # --- JAVASCRIPT EXTRACTION WITH DOM-LEVEL DESTINATION CHECK ---
                    js_extract = f"""() => {{
                        let records = [];
                        let cards = document.querySelectorAll('.main-bo-lis, .fltResult');
                        
                        cards.forEach(card => {{
                            let cardText = card.innerText || "";
                            let lowerText = cardText.toLowerCase();

                            // 1. Strict Stop Element Check (.dura_md2)
                            let stopEl = card.querySelector('.dura_md2, [class*="dura"]');
                            if (!stopEl) return;
                            let stopText = stopEl.innerText.toLowerCase().trim();
                            if (!stopText.includes('non-stop') && !stopText.includes('non stop') && !stopText.includes('0 stop') && !stopText.includes('nonstop')) return;

                            // 2. Strict DOM-Level Destination City Node Check (.txt-r3-n)
                            let cityNodes = card.querySelectorAll('.txt-r3-n');
                            if (cityNodes.length < 2) return;
                            let arrivalCity = cityNodes[cityNodes.length - 1].innerText.toLowerCase().trim();
                            
                            // Reject secondary or adjacent airports directly at the DOM layer
                            if (arrivalCity.includes('navi mumbai') || arrivalCity.includes('ghaziabad') || arrivalCity.includes('hindon') || arrivalCity.includes('noida')) {{
                                return;
                            }}

                            // 3. Extract Airline
                            let airlineEl = card.querySelector('.tx-thme, .air-line-name, span.txt-r4, .airline-name');
                            let rawAirline = airlineEl ? airlineEl.innerText.trim() : "Unknown Airline";
                            let actualAirline = rawAirline.replace(/Operated by|Partner/gi, '').trim();
                            if (!actualAirline) actualAirline = "EaseMyTrip Partner";

                            // 4. Extract Price
                            let priceEl = card.querySelector('.txt-r6, .txt-r6-n, .price');
                            let cleanNum = 0;
                            if (priceEl && priceEl.innerText) {{
                                cleanNum = parseInt(priceEl.innerText.replace(/[^0-9]/g, ''));
                            }} else {{
                                let pMatch = cardText.match(/[₹|Rs]\\s*([\\d,]+)/);
                                if (pMatch) cleanNum = parseInt(pMatch[1].replace(/,/g, ''));
                            }}
                            if (isNaN(cleanNum) || cleanNum < 1500) return;

                            // 5. Extract & Clean Flight Number (Fixes spacing like "6E- 324")
                            let flightEl = card.querySelector('.txt-r5');
                            let flightNo = "Unknown";
                            if (flightEl && flightEl.innerText) {{
                                flightNo = flightEl.innerText.replace(/\\s+/g, ' ').replace('\\n', '').trim();
                                flightNo = flightNo.replace(/-\\s+/, '-'); // Standardize hyphen spacing
                            }} else {{
                                let fMatch = cardText.match(/([A-Z0-9]{{2}})[-\\s]?(\\d{{3,4}})/i);
                                if (fMatch) flightNo = fMatch[1].toUpperCase() + "-" + fMatch[2];
                            }}

                            // 6. Extract Departure Time
                            let depTime = "Unknown";
                            let timeMatches = cardText.match(/\\b(\\d{{2}}:\\d{{2}})\\b/g);
                            if (timeMatches && timeMatches.length > 0) {{
                                depTime = timeMatches[0];
                            }}

                            records.push({{
                                airline: actualAirline,
                                flight_no: flightNo,
                                departure_time: depTime,
                                fare: cleanNum
                            }});
                        }});
                        
                        // Deduplicate identical rows
                        let unique = {{}};
                        records.forEach(f => {{
                            let key = f.flight_no + "_" + f.departure_time;
                            if (!unique[key] || f.fare < unique[key].fare) {{
                                unique[key] = f;
                            }}
                        }});
                        return Object.values(unique);
                    }}"""
                    
                    extracted_flights = page.evaluate(js_extract)

                    if extracted_flights:
                        print(f"✅ Extracted {len(extracted_flights)} strictly verified Non-Stop flights.")
                        for idx, f in enumerate(extracted_flights):
                            base = round(f['fare'] * 0.85, 2)
                            tax = round(f['fare'] * 0.15, 2)
                            print(f" {idx+1:2d}. [{f['airline']}] Flight: {f['flight_no']} | Dept: {f['departure_time']} | Base: ₹{base} | Tax: ₹{tax} | Total: ₹{f['fare']}")
                    else:
                        print("⚠️ Zero valid non-stop flights extracted.")

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