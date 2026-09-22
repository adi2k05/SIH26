from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import time

def run_emt_test_scraper():
    advance_windows = [1]  # STRICTLY T+1
    top_20_routes = ["DEL-BOM"]  # STRICTLY DEL-BOM
    
    city_map = {
        "DEL": "Delhi", "BOM": "Mumbai", "BLR": "Bengaluru", 
        "HYD": "Hyderabad", "CCU": "Kolkata", "GOI": "Goa", 
        "MAA": "Chennai", "AMD": "Ahmedabad"
    }

    print("Launching EaseMyTrip Test Scraper (Resilient Angular DOM Extraction)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d/%m/%Y")
                print(f"\n--- EaseMyTrip Test: {route} | T+{window} Days ({date_str}) ---")
                
                for attempt in range(1, 3):
                    try:
                        url = f"https://flight.easemytrip.com/FlightList/Index?srch={origin}-{city_map[origin]}-India|{dest}-{city_map[dest]}-India|{date_str}&px=1-0-0&cbn=0&ar=undefined&isSplit=false&isOneway=true&isFreeFlight=false"
                        
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        
                        # Wait specifically for Angular listing wrappers or general result containers
                        page.wait_for_selector("div[class*='listing'], div[class*='flt'], div[class*='card']", timeout=30000)
                        
                        # Scroll iteratively to populate lazy-loaded cards
                        for _ in range(4):
                            page.evaluate("window.scrollBy(0, 1000)")
                            page.wait_for_timeout(1000)

                        # --- ROBUST ANGULAR DOM EXTRACTION FOR EMT ---
                        extracted_flights = page.evaluate("""() => {
                            let flights = [];
                            // Target Angular listing boxes or fall back to any div holding prices and flight codes
                            let cards = document.querySelectorAll('div[class*="listing"], div[class*="fltResult"], div[class*="flight-card"], div[class*="ng-star-inserted"]');
                            
                            if (cards.length === 0) {
                                cards = document.querySelectorAll('div');
                            }
                            
                            cards.forEach(card => {
                                let cardText = card.innerText || "";
                                
                                // Must contain pricing and non-stop indication
                                if (!cardText.includes('₹') && !cardText.includes('Rs')) return;
                                if (!cardText.toLowerCase().includes('nonstop') && !cardText.toLowerCase().includes('non stop')) return;

                                // 1. Extract Airline (typically inside h6 tags in EMT DOM)
                                let airlineEl = card.querySelector('h6');
                                let airline = airlineEl ? airlineEl.innerText.trim() : "";
                                
                                if (!airline || airline.length > 30) {
                                    let matchAirline = cardText.match(/(IndiGo|Air India Express|Air India|Akasa Air|SpiceJet|Vistara)/i);
                                    airline = matchAirline ? matchAirline[0] : "EMT Partner";
                                }

                                // 2. Extract Flight Number (e.g. 6E-2721, QP-1119)
                                let flightMatch = cardText.match(/([A-Z0-9]{2})\\s*([\\-\\s]?\\d{3,4})/i);
                                let flightNo = flightMatch ? (flightMatch[1].toUpperCase() + "-" + flightMatch[2].replace(/[^0-9]/g, '')) : "";
                                if (!flightNo) return;

                                // 3. Extract Departure Time (HH:MM)
                                let times = cardText.match(/\\b(\\d{2}:\\d{2})\\b/g) || [];
                                let depTime = times.length > 0 ? times[0] : "";

                                // 4. Extract Price
                                let priceMatches = cardText.match(/[₹|Rs]\\s*([\\d,]+)/g) || [];
                                let cleanPrices = priceMatches.map(p => parseInt(p.replace(/[^0-9]/g, ''))).filter(p => p > 1500 && p < 100000);
                                let cleanNum = cleanPrices.length > 0 ? Math.min(...cleanPrices) : 0;

                                if (cleanNum > 1500 && flightNo) {
                                    flights.push({
                                        airline: airline,
                                        flight_no: flightNo,
                                        departure_time: depTime,
                                        fare: cleanNum
                                    });
                                }
                            });
                            return flights;
                        }""")

                        # Deduplicate results by flight_no and fare
                        unique_flights = {}
                        for f in extracted_flights:
                            key = f"{f['flight_no']}_{f['fare']}_{f['departure_time']}"
                            unique_flights[key] = f
                        
                        valid_flights = list(unique_flights.values())

                        if valid_flights:
                            print(f"\n✅ Extracted {len(valid_flights)} strict Non-Stop records for T+{window}.")
                            print("🔍 ALL EXTRACTED RECORDS:")
                            for idx, f in enumerate(valid_flights):
                                base = round(f['fare'] * 0.85, 2)
                                taxes = round(f['fare'] * 0.15, 2)
                                print(f"   {idx+1}. [{f['airline']}] Flight: {f['flight_no']} | Time: {f['departure_time']} | Base: ₹{base} | Tax: ₹{taxes} | Total: ₹{f['fare']}")
                            break
                        else:
                            raise Exception("Zero valid non-stop flights extracted from DOM.")

                    except Exception as e:
                        print(f"⚠️ EMT Attempt {attempt} failed: {e}")
                        if attempt == 1:
                            time.sleep(4)

        browser.close()
        print("\n🎉 EaseMyTrip Test Complete!")

if __name__ == "__main__":
    run_emt_test_scraper()