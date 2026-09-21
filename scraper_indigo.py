from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import sqlite3
import random
import time
import os
import sys
import threading

# --- HOTFIX FOR WinError 6 ---
original_excepthook = threading.excepthook
def suppress_winerror6_excepthook(args):
    if issubclass(args.exc_type, OSError) and getattr(args.exc_value, 'winerror', None) == 6:
        pass 
    else:
        original_excepthook(args)
threading.excepthook = suppress_winerror6_excepthook

original_sys_excepthook = sys.excepthook
def suppress_winerror6_sys_excepthook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, OSError) and getattr(exc_value, 'winerror', None) == 6:
        pass
    else:
        original_sys_excepthook(exc_type, exc_value, exc_traceback)
sys.excepthook = suppress_winerror6_sys_excepthook
# -----------------------------

def is_already_scraped(route, window, source):
    if os.environ.get("FORCE_RESCRAPE") == "1":
        return False
    if not os.path.exists('airfare_index.db'):
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

def scrape_indigo_route(page, origin: str, dest: str, window_days: int):
    target_date = datetime.now() + timedelta(days=window_days)
    target_yyyy_mm_dd = target_date.strftime("%Y-%m-%d")  
    display_date = target_date.strftime("%d/%m/%Y")
    
    print(f"\n--- IndiGo Scraping: {origin} -> {dest} | T+{window_days} Days ({display_date}) ---")

    # 1. Load Homepage
    page.goto("https://www.goindigo.in/", wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)

    # Nuke Cookie Banners and Promos via JS
    page.evaluate("""() => {
        let overlays = document.querySelectorAll('.cookie-policy, [class*="cookie"], [class*="overlay"], .loginModal');
        overlays.forEach(el => el.remove());
        document.body.style.overflow = 'auto';
    }""")
    time.sleep(1)

    # Ensure 'One Way' trip type is active
    try:
        page.locator("label:has-text('One Way'), input[value='one-way']").first.click(force=True, timeout=2000)
    except Exception:
        pass

    # 2. Select Origin
    print(f"📍 Selecting Origin: {origin}...")
    page.locator("div[class*='search-widget-form-body__from']").first.click(force=True)
    time.sleep(1)
    
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(origin, delay=150)
    time.sleep(1.5)
    
    origin_item = page.locator(f"div.city-selection__list-item:has-text('{origin}')").first
    origin_item.wait_for(state="attached", timeout=5000)
    origin_item.click(force=True)
    time.sleep(1.2)

    # 3. Select Destination
    print(f"📍 Selecting Destination: {dest}...")
    page.locator("div[class*='search-widget-form-body__to']").first.click(force=True)
    time.sleep(1)
    
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(dest, delay=150)
    time.sleep(1.5)
    
    dest_item = page.locator(f"div.city-selection__list-item:has-text('{dest}')").first
    dest_item.wait_for(state="attached", timeout=5000)
    dest_item.click(force=True)
    time.sleep(1.2)

    # 4. Select Departure Date (BULLETPROOF ASYNC JS CALENDAR NAVIGATOR)
    print(f"📅 Selecting Date: {display_date} (target code: {target_yyyy_mm_dd})...")
    
    page.locator("div[class*='search-widget-form-body__departure']").first.click(force=True)
    time.sleep(1.5)

    # This async JS function executes natively in the browser, immune to DOM detachment
    js_calendar_nav = f"""
    async () => {{
        let targetDate = "{target_yyyy_mm_dd}";
        let maxFlips = 6;
        
        for (let i = 0; i < maxFlips; i++) {{
            let cell = document.querySelector(`div[data-date="${{targetDate}}"]`);
            if (cell) {{
                let btn = cell.closest('button') || cell;
                btn.click();
                btn.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true }}));
                return true;
            }}
            
            let nextBtn = document.querySelector('button.rdrNextButton, button[class*="next"], button[class*="Next"]');
            if (nextBtn) {{
                nextBtn.click();
                await new Promise(r => setTimeout(r, 900)); // Wait for React re-render
            }} else {{
                break;
            }}
        }}
        return false;
    }}
    """
    
    date_clicked = page.evaluate(js_calendar_nav)
    if not date_clicked:
        raise RuntimeError(f"Could not locate calendar day {target_yyyy_mm_dd} in picker.")
    time.sleep(1.2)

    # 5. Submit Search
    print("🚀 Submitting Search...")
    page.locator("div[class*='search-btn'] button, button.skyplus-button--filled-primary").first.click(force=True)

    # 6. Wait for Results Page
    print("⏳ Waiting for flight selection page...")
    
    try:
        page.wait_for_selector(".fare-accordion, div[class*='fare-accordion'], .no-flights-found", timeout=45000)
    except:
        pass
        
    time.sleep(3)
    
    body_text = page.locator("body").inner_text().lower()
    if "no flights found" in body_text or "sold out" in body_text:
        print(f"ℹ️ IndiGo returned no flights for T+{window_days}. Logging NULL.")
        return "EMPTY"

    print("📜 Scrolling to load all rendered flight cards...")
    for _ in range(6):
        page.evaluate("window.scrollBy(0, 800);")
        time.sleep(1.2)

    # 7. Extract Flight Cards
    js_extract = f"""
    () => {{
        let records = [];
        let cards = document.querySelectorAll('.fare-accordion, div[class*="fare-accordion"]');

        cards.forEach(card => {{
            let cardText = card.innerText || "";
            let lines = cardText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

            let flightNumEl = card.querySelector('.flight-number, div[class*="flight-number"]');
            let flightNum = flightNumEl ? flightNumEl.innerText.replace(/\\s+/g, ' ').trim() : "";
            if (!flightNum) {{
                let m = cardText.match(/6E[-\\s]?\\d{{3,4}}/i);
                flightNum = m ? m[0].replace(' ', '-') : "6E-IndiGo";
            }} else {{
                flightNum = flightNum.replace(' ', '-');
            }}

            let times = cardText.match(/\\b(\\d{{2}}:\\d{{2}})\\b/g) || [];
            let departureTime = times.length > 0 ? times[0] : "";

            let priceMatches = cardText.match(/[₹|Rs]\\s*([\\d,]+)/g) || [];
            let cleanPrices = priceMatches.map(p => parseInt(p.replace(/[^0-9]/g, ''))).filter(p => p > 1500 && p < 100000);

            if (cleanPrices.length > 0) {{
                let totalFare = Math.min(...cleanPrices);
                records.push({{
                    airline: "IndiGo",
                    flight_number: flightNum,
                    departure_time: departureTime,
                    total_fare: totalFare
                }});
            }}
        }});
        return records;
    }}
    """
    raw_flights = page.evaluate(js_extract)

    unique_flights = {}
    for f in raw_flights:
        key = f"{f['flight_number']}_{f['departure_time']}_{f['total_fare']}"
        if key not in unique_flights:
            total = f["total_fare"]
            base = round(total * 0.85, 2)
            taxes = round(total * 0.15, 2)
            unique_flights[key] = {
                "airline": f["airline"],
                "flight_number": f["flight_number"],
                "route": f"{origin}-{dest}",
                "advance_window_days": window_days,
                "departure_time": f["departure_time"],
                "base_fare": base,
                "taxes_fees": taxes,
                "total_fare": total,
                "travel_date": display_date,
                "ota_source": "IndiGo Direct"
            }

    flight_list = list(unique_flights.values())
    print(f"✅ Extracted {len(flight_list)} direct IndiGo flights!")
    return flight_list


def run_indigo_pipeline():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]

    print("Launching IndiGo Pipeline Scraper (Full 20-Route Suite)...")

    user_data_dir = os.path.join(os.getcwd(), "indigo_browser_profile")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            channel="chrome",
            headless=False,
            viewport={"width": 1920, "height": 1080},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--test-type"
            ],
            ignore_default_args=["--enable-automation"]
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            for route in top_20_routes:
                origin, dest = route.split("-")
                print(f"\n==================================================")
                print(f"🛫 STARTING ROUTE: {route}")
                print(f"==================================================")
                
                for window in advance_windows:
                    if is_already_scraped(route, window, "IndiGo Direct"):
                        print(f"⏩ IndiGo: {route} | T+{window} already collected today. Skipping.")
                        continue

                    try:
                        records = scrape_indigo_route(page, origin, dest, window)
                        
                        with sqlite3.connect("airfare_index.db") as conn:
                            conn.execute("""
                                CREATE TABLE IF NOT EXISTS raw_fares (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                    airline TEXT, route TEXT, advance_window_days INTEGER,
                                    base_fare REAL, taxes_fees REAL, total_fare REAL,
                                    ota_source TEXT, departure_time TEXT, flight_no TEXT
                                )
                            """)
                            
                            if records == "EMPTY":
                                conn.execute('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time)
                                    VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?)
                                ''', ("IndiGo", route, window, "IndiGo Direct"))
                            elif records:
                                rows = [
                                    (
                                        r["airline"], r["route"], r["advance_window_days"],
                                        r["base_fare"], r["taxes_fees"], r["total_fare"],
                                        r["ota_source"], r["departure_time"], r["flight_number"]
                                    )
                                    for r in records
                                ]
                                conn.executemany("""
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, rows)
                                
                            conn.commit()
                            
                        if records != "EMPTY":
                            print(f"💾 Successfully saved {len(records)} records for T+{window}.")
                            
                    except Exception as e:
                        print(f"⚠️ Failed to scrape {route} (T+{window}): {e}")

                    jitter = random.uniform(4.0, 7.0)
                    print(f"⏳ Cooling down for {round(jitter, 1)}s...")
                    time.sleep(jitter)
                
                route_jitter = random.uniform(10.0, 15.0)
                print(f"\n⏳ Route complete. Cooling down for {round(route_jitter, 1)}s before next route...")
                time.sleep(route_jitter)
                
        finally:
            context.close()

    print("\n🎉 IndiGo Pipeline Batch Scraping Complete!")

if __name__ == "__main__":
    run_indigo_pipeline()
    os._exit(0)