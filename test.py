from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import time

def run_emt_test_scraper():
    origin = "DEL"
    dest = "BOM"
    window = 1  # STRICTLY T+1
    
    city_map = {
        "DEL": "Delhi", "BOM": "Mumbai", "BLR": "Bengaluru", 
        "HYD": "Hyderabad", "CCU": "Kolkata", "GOI": "Goa", 
        "MAA": "Chennai", "AMD": "Ahmedabad"
    }

    future_date_obj = datetime.now() + timedelta(days=window)
    date_str = future_date_obj.strftime("%d/%m/%Y")
    
    print(f"Launching EaseMyTrip Test Scraper ({origin}-{dest} | T+{window})...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        try:
            url = f"https://flight.easemytrip.com/FlightList/Index?srch={origin}-{city_map[origin]}-India|{dest}-{city_map[dest]}-India|{date_str}&px=1-0-0&cbn=0&ar=undefined&isSplit=false&isOneway=true&isFreeFlight=false"
            
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            # Use original proven selector
            page.wait_for_selector(".fltResult, div[id^='divFlightResult'], .flight-card", timeout=30000)
            
            # Quick scroll to populate lazy elements
            page.evaluate("window.scrollBy(0, 1500)")
            page.wait_for_timeout(2000)

            extracted_flights = page.evaluate(f"""() => {{
                let flights = [];
                let cards = document.querySelectorAll('.fltResult, div[id^="divFlightResult"], .flight-card');
                
                cards.forEach(card => {{
                    let cardText = card.innerText || "";
                    let lowerText = cardText.toLowerCase();
                    
                    // 1. Strict Non-Stop Check
                    if (!lowerText.includes('nonstop') && !lowerText.includes('non stop')) return;
                    
                    // 2. Strict Route Check (ensures DEL and BOM are inside the card text)
                    if (!cardText.includes('{origin}') || !cardText.includes('{dest}')) return;

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
                        let match = cardText.match(/[₹|Rs]\\s*([\\d,]+)/);
                        if (match) cleanNum = parseInt(match[1].replace(/,/g, ''));
                    }}

                    if (isNaN(cleanNum) || cleanNum <= 1500) return;

                    // 5. Extract Flight Number via Regex
                    let flightMatch = cardText.match(/([A-Z0-9]{2})[-\\s]?(\\d{3,4})/i);
                    let flightNo = flightMatch ? (flightMatch[1].toUpperCase() + "-" + flightMatch[2]) : "EMT-Flight";

                    // 6. Extract Departure Time via Regex
                    let timeMatches = cardText.match(/\\b(\\d{2}:\\d{2})\\b/g);
                    let depTime = timeMatches && timeMatches.length > 0 ? timeMatches[0] : "";

                    flights.push({{
                        airline: actualAirline,
                        flight_no: flightNo,
                        departure_time: depTime,
                        fare: cleanNum
                    }});
                }});
                
                // Deduplicate
                let unique = {{}};
                flights.forEach(f => {{
                    let key = f.flight_no + "_" + f.fare + "_" + f.departure_time;
                    if (!unique[key]) unique[key] = f;
                }});
                return Object.values(unique);
            }}""")

            if extracted_flights:
                print(f"\n✅ Extracted {len(extracted_flights)} strict Non-Stop records for T+{window}.")
                print("🔍 ALL EXTRACTED RECORDS:")
                for idx, f in enumerate(extracted_flights):
                    base = round(f['fare'] * 0.85, 2)
                    tax = round(f['fare'] * 0.15, 2)
                    print(f"   {idx+1}. [{f['airline']}] Flight: {f['flight_no']} | Time: {f['departure_time']} | Base: ₹{base} | Tax: ₹{tax} | Total: ₹{f['fare']}")
            else:
                print("⚠️ Zero valid non-stop flights extracted.")

        except Exception as e:
            print(f"⚠️ Test failed: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    run_emt_test_scraper()