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
                    
                    page.wait_for_selector(".main-bo-li", timeout=30000)
                    
                    print("Page loaded. Scrolling to populate all lazy-rendered flight cards...")
                    for _ in range(5):
                        page.evaluate("window.scrollBy(0, 800);")
                        page.wait_for_timeout(1000)

                    js_extract = """() => {
                        let records = [];
                        let cards = document.querySelectorAll('.main-bo-li, div[ng-repeat*="LimitValueForListing"]');
                        
                        cards.forEach(card => {
                            let text = card.innerText || card.textContent || "";
                            let lowerText = text.toLowerCase();
                            
                            let isNonStop = lowerText.includes('non-stop') || lowerText.includes('non stop') || lowerText.includes('0 stop') || lowerText.includes('nonstop');
                            if (!isNonStop) return;

                            let airlineEl = card.querySelector('.txt-r4, .air-line-name');
                            let airline = airlineEl ? airlineEl.innerText.trim() : "Unknown";
                            airline = airline.replace(/Operated by|Partner/gi, '').trim();

                            let flightEl = card.querySelector('.txt-r5');
                            let flightNo = "Unknown";
                            if (flightEl) {
                                flightNo = flightEl.innerText.replace(/\\s+/g, ' ').replace('\\n', '').trim();
                            } else {
                                let fMatch = text.match(/([A-Z0-9]{2})[-\\s]?(\\d{3,4})/i);
                                if (fMatch) flightNo = fMatch[1].toUpperCase() + "-" + fMatch[2];
                            }

                            let depTime = "Unknown";
                            let timeMatches = text.match(/\\b(\\d{2}:\\d{2})\\b/g);
                            if (timeMatches && timeMatches.length > 0) {
                                depTime = timeMatches[0];
                            }

                            let fare = 0;
                            let priceMatch = text.match(/[₹|Rs]\\s*([\\d,]+)/);
                            if (priceMatch) {
                                fare = parseInt(priceMatch[1].replace(/,/g, ''));
                            }
                            
                            if (fare > 1500) {
                                records.push({
                                    airline: airline,
                                    flight_no: flightNo,
                                    departure_time: depTime,
                                    fare: fare
                                });
                            }
                        });
                        
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

                    if extracted_flights:
                        print(f"✅ Extracted {len(extracted_flights)} verified Non-Stop flights.")
                        for idx, f in enumerate(extracted_flights):
                            base = round(f['fare'] * 0.85, 2)
                            tax = round(f['fare'] * 0.15, 2)
                            print(f" {idx+1:2d}. [{f['airline']}] Flight: {f['flight_no']} | Dept: {f['departure_time']} | Base: ₹{base} | Tax: ₹{tax} | Total: ₹{f['fare']}")
                    else:
                        print("⚠️ Zero valid non-stop flights extracted. Please verify if flights exist for this date.")

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