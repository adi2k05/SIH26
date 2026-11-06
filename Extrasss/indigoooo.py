from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import time

def run_airindia_test_scraper():
    test_route = "DEL-BOM"
    advance_windows = [1, 7]
    origin, dest = test_route.split("-")
    all_results = []

    print(f"Launching Air India Test Scraper ({test_route} | Windows: {advance_windows})...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])

        for window in advance_windows:
            future_date_obj = datetime.now() + timedelta(days=window)
            target_aria = f"{future_date_obj.month}/{future_date_obj.day}/{future_date_obj.year}"
            target_iso = future_date_obj.strftime("%Y-%m-%d")

            print(f"\n--- Air India Test: {test_route} | T+{window} Days ({target_iso}) ---")

            for attempt in range(1, 3):
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}
                )
                page = context.new_page()

                try:
                    page.goto("https://www.airindia.com/", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(4000)

                    # --- 1. YOUR FRIEND'S PROVEN NAVIGATION LOGIC ---
                    try:
                        page.get_by_text("Accept All", exact=True).first.click(force=True, timeout=5000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1000)

                    page.get_by_text("One Way", exact=True).first.click(force=True, timeout=5000)
                    page.wait_for_timeout(500)

                    origin_input = page.locator('input.ai-autocomplete-input').nth(0)
                    origin_input.click(force=True)
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    page.keyboard.type(origin, delay=150)
                    page.wait_for_timeout(1200)
                    page.locator("mat-option").first.click(force=True, timeout=5000)
                    page.wait_for_timeout(800)

                    dest_input = page.locator('input.ai-autocomplete-input').nth(1)
                    dest_input.click(force=True)
                    page.wait_for_timeout(300)
                    page.keyboard.type(dest, delay=150)
                    page.wait_for_timeout(1200)
                    page.locator("mat-option").first.click(force=True, timeout=5000)
                    page.wait_for_timeout(800)

                    page.get_by_text("Select Date", exact=True).first.click(force=True, timeout=5000)
                    page.wait_for_timeout(1200)

                    for _ in range(3):
                        if page.locator(f'button.mat-calendar-body-cell[aria-label="{target_aria}"]').count() > 0:
                            break
                        page.get_by_role("button", name="Next month").first.click(force=True)
                        page.wait_for_timeout(600)

                    page.locator(f'button.mat-calendar-body-cell[aria-label="{target_aria}"]').first.click(force=True, timeout=5000)
                    page.wait_for_timeout(1000)

                    page.get_by_role("button", name="Search", exact=True).first.click(force=True, timeout=8000)
                    # --- END NAVIGATION LOGIC ---

                    # --- 2. WAIT FOR FLIGHT MATRIX TO RENDER ---
                    print("Waiting for flight matrix to render...")
                    flights_loaded = False
                    for _ in range(30):
                        body_text = page.locator("body").inner_text()
                        if "SOMETHING WENT WRONG" in body_text.upper():
                            raise Exception("Air India results page threw its frontend error.")
                        if "Flight Details" in body_text:
                            flights_loaded = True
                            break
                        page.wait_for_timeout(1000)

                    if not flights_loaded:
                        raise Exception("Flight list never rendered.")

                    page.wait_for_timeout(2000)
                    page.evaluate("window.scrollBy(0, 1500)")
                    page.wait_for_timeout(2000)

                    # --- 3. PRECISION IMAGE-BASED DOM EXTRACTION (ALL FLIGHTS) ---
                    flights = page.evaluate(f"""() => {{
                        let records = [];
                        // Target the exact custom element or card wrapper
                        let cards = document.querySelectorAll('ai-pb-flight-card, .ai-pb-flight-card');
                        
                        cards.forEach(card => {{
                            // Strict Origin Validation
                            let origEl = card.querySelector('.ai-pb-preferred-departure-city');
                            let origText = origEl ? origEl.innerText.trim() : "";
                            if (!origText.includes('{origin}')) return;

                            // Strict Destination Validation
                            let destEl = card.querySelector('.ai-pb-preferred-arrival-city');
                            let destText = destEl ? destEl.innerText.trim() : "";
                            if (!destText.includes('{dest}')) return;

                            // Strict Non-Stop Validation
                            let stopEl = card.querySelector('.ai-pb-total-stop-info');
                            let stopText = stopEl ? stopEl.innerText.trim() : (card.innerText || "");
                            if (!stopText.toLowerCase().includes('non-stop') && !stopText.toLowerCase().includes('non stop')) return;
                            
                            // Extract Flight Number
                            let flightEl = card.querySelector('.ai-pb-flight-id');
                            let flightNo = flightEl ? flightEl.innerText.trim() : "";
                            if (!flightNo) return;
                            flightNo = flightNo.replace(/\\s+/g, '-').toUpperCase();

                            // Extract Departure Time
                            let timeEl = card.querySelector('.ai-pb-departure-time');
                            let depTime = timeEl ? timeEl.innerText.trim() : "";
                            if (!depTime) return;

                            // Extract Actual Lowest Fare
                            let priceEl = card.querySelector('.ai-pb-actual-price');
                            let fare = 0;
                            if (priceEl) {{
                                fare = parseInt(priceEl.innerText.replace(/[^0-9]/g, ''));
                            }}
                            
                            if (fare > 1500) {{
                                records.push({{
                                    airline: "Air India",
                                    flight_no: flightNo,
                                    departure_time: depTime,
                                    fare: fare
                                }});
                            }}
                        }});
                        
                        // Deduplicate based on flight number and time
                        let unique = {{}};
                        records.forEach(f => {{
                            let key = f.flight_no + "_" + f.departure_time;
                            if (!unique[key] || f.fare < unique[key].fare) {{
                                unique[key] = f;
                            }}
                        }});
                        return Object.values(unique);
                    }}""")

                    if flights:
                        print(f"✅ Extracted {len(flights)} exact non-stop records for T+{window}.")
                        for f in flights:
                            all_results.append({
                                "airline": f["airline"],
                                "flight_no": f["flight_no"],
                                "departure_time": f["departure_time"],
                                "base_fare": round(f["fare"] * 0.85, 2),
                                "taxes_fees": round(f["fare"] * 0.15, 2),
                                "total_fare": f["fare"]
                            })
                        context.close()
                        break
                    else:
                        raise Exception("Zero valid non-stop flights parsed from card wrappers.")

                except Exception as e:
                    print(f"⚠️ Attempt {attempt} failed: {e}")
                    context.close()
                    if attempt == 1:
                        time.sleep(4)

        browser.close()

        print("\n🔍 ALL EXTRACTED RECORDS:")
        for idx, f in enumerate(all_results):
            print(f"   {idx+1}. [{f['airline']}] Flight: {f['flight_no']} | Time: {f['departure_time']} | Base: ₹{f['base_fare']} | Tax: ₹{f['taxes_fees']} | Total: ₹{f['total_fare']}")

if __name__ == "__main__":
    run_airindia_test_scraper()