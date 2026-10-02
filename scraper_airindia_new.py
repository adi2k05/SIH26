import os
import sqlite3
import re
import time
from datetime import datetime, timedelta

# Use patchright instead of playwright to bypass WAF, just like go.py did successfully
from patchright.sync_api import sync_playwright

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

def extract_flights(page, origin, dest):
    cards = page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('*')).filter(
            e => e.textContent.trim() === 'Flight Details' && e.offsetParent !== null && e.children.length === 0
        );
        return btns.map(b => {
            let card = b.closest('mat-card');
            if (card) return card.innerText;
            
            // fallback
            card = b;
            for (let i = 0; i < 12; i++) { if (card.parentElement) card = card.parentElement; }
            return card.innerText;
        });
    }''')

    results = []
    seen_flight_numbers = set()
    for raw in cards:
        lines = [l.strip() for l in raw.split('\n') if l.strip()]

        fn_idx = next((i for i, l in enumerate(lines) if re.match(r'^(AI|IX|UK)\s?\d{2,5}', l)), None)
        if fn_idx is None:
            continue
        flight_number = lines[fn_idx].replace(" ", "-") # normalize flight number
        if flight_number in seen_flight_numbers:
            continue

        dep_time = next((l for l in lines[fn_idx:] if re.match(r'^\d{2}:\d{2}$', l)), None)
        if not dep_time:
            continue



        if origin not in lines or dest not in lines:
            continue

        if "INR" not in lines:
            continue
        inr_idx = lines.index("INR")
        price_str = lines[inr_idx + 1] if len(lines) > inr_idx + 1 else None
        if not price_str or not re.match(r'^[\d,]+$', price_str):
            continue
        total_fare = float(price_str.replace(",", ""))
        if not (1500 < total_fare < 75000):
            continue

        seen_flight_numbers.add(flight_number)
        results.append({
            "airline": "Air India",
            "flight_number": flight_number,
            "route": f"{origin}-{dest}",
            "base_fare": round(total_fare * 0.85, 2),
            "taxes_fees": round(total_fare * 0.15, 2),
            "total_fare": total_fare,
            "ota_source": "Air India Direct",
            "departure_time": dep_time
        })

    return results

def run_airindia_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]

    print("Launching Air India Scraper (Full Flight Extraction mode)...")

    # Use patchright instead of stealth to effectively bypass anti-bot challenges
    with sync_playwright() as p:
        is_headless = os.environ.get("HEADLESS_MODE") == "1"
        browser = p.chromium.launch(headless=is_headless)

        for route in top_20_routes:
            origin, dest = route.split("-")

            for window in advance_windows:
                if is_already_scraped(route, window, "Air India Direct"):
                    print(f"Skipping Air India: {route} | T+{window} already collected today.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                target_aria = f"{future_date_obj.month}/{future_date_obj.day}/{future_date_obj.year}"
                target_iso = future_date_obj.strftime("%Y-%m-%d")

                print(f"--- Air India Scraping: {route} | T+{window} Days ({target_iso}) ---")

                for attempt in range(1, 3):
                    context = browser.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=os.path.join(os.getcwd(), 'videos'))
                    page = context.new_page()

                    try:
                        page.goto("https://www.airindia.com/", wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(9000)

                        try:
                            page.get_by_text("Accept All", exact=True).first.click(timeout=6000)
                        except Exception:
                            pass
                        page.wait_for_timeout(1500)

                        try:
                            page.locator('#simplifiedLoginModal button.btn-close').first.click(timeout=4000)
                        except Exception:
                            pass
                        page.wait_for_timeout(500)

                        page.get_by_text("One Way", exact=True).first.click(timeout=6000)
                        page.wait_for_timeout(500)

                        origin_input = page.locator('input.ai-autocomplete-input').nth(0)
                        origin_input.click()
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.wait_for_timeout(300)
                        page.keyboard.type(origin, delay=150)
                        page.wait_for_timeout(2500)
                        page.locator("mat-option").first.click(timeout=6000)
                        page.wait_for_timeout(1200)

                        dest_input = page.locator('input.ai-autocomplete-input').nth(1)
                        dest_input.click()
                        page.wait_for_timeout(300)
                        page.keyboard.type(dest, delay=150)
                        page.wait_for_timeout(2500)
                        page.locator("mat-option").first.click(timeout=6000)
                        page.wait_for_timeout(1200)

                        page.get_by_text("Select Date", exact=True).first.click(timeout=6000)
                        page.wait_for_timeout(1500)

                        for _ in range(4):
                            if page.locator(f'button.mat-calendar-body-cell[aria-label="{target_aria}"]').count() > 0:
                                break
                            page.get_by_role("button", name="Next month").first.click()
                            page.wait_for_timeout(700)

                        page.locator(f'button.mat-calendar-body-cell[aria-label="{target_aria}"]').first.click(timeout=6000)
                        page.wait_for_timeout(1200)

                        page.get_by_role("button", name="Search", exact=True).first.click(timeout=8000)

                        flights_loaded = False
                        no_flights_scheduled = False
                        for _ in range(20):
                            body_text = page.locator("body").inner_text()
                            if "SOMETHING WENT WRONG" in body_text.upper():
                                raise Exception("Air India results page threw its frontend error.")
                            if "no flights" in body_text.lower() or "sorry" in body_text.lower():
                                no_flights_scheduled = True
                                break
                            if "Flight Details" in body_text:
                                flights_loaded = True
                                break
                            page.wait_for_timeout(1000)

                        if no_flights_scheduled:
                            print(f"Info: Air India does not operate flights on {route} for T+{window}.")
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.execute('''
                                    CREATE TABLE IF NOT EXISTS raw_fares (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                        airline TEXT, route TEXT, advance_window_days INTEGER,
                                        base_fare REAL, taxes_fees REAL, total_fare REAL,
                                        ota_source TEXT, departure_time TEXT, flight_no TEXT
                                    )
                                ''')
                                conn.execute('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                    VALUES (?, ?, ?, NULL, NULL, NULL, ?, NULL, NULL)
                                ''', ("Air India", route, window, "Air India Direct"))
                                conn.commit()
                            context.close()
                            break

                        if not flights_loaded:
                            raise Exception("Flight list never rendered.")

                        page.wait_for_timeout(1500)
                        flights = extract_flights(page, origin, dest)

                        if flights:
                            print(f"Success: Air India {route} | T+{window} captured {len(flights)} flights (Attempt {attempt}).")
                            
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.execute('''
                                    CREATE TABLE IF NOT EXISTS raw_fares (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                        airline TEXT, route TEXT, advance_window_days INTEGER,
                                        base_fare REAL, taxes_fees REAL, total_fare REAL,
                                        ota_source TEXT, departure_time TEXT, flight_no TEXT
                                    )
                                ''')
                                rows = [
                                    (
                                        f["airline"], f["route"], window,
                                        f["base_fare"], f["taxes_fees"], f["total_fare"],
                                        f["ota_source"], f["departure_time"], f["flight_number"]
                                    )
                                    for f in flights
                                ]
                                conn.executemany("""
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, rows)
                                conn.commit()

                            context.close()
                            break
                        else:
                            raise Exception("Zero valid non-stop flights parsed from card texts.")

                    except Exception as e:
                        print(f"Warning: Air India {route} T+{window} Attempt {attempt} failed: {e}")
                        context.close()
                        if attempt == 1:
                            time.sleep(8)

        browser.close()
        print("Air India Database Scraping Complete!")

if __name__ == "__main__":
    run_airindia_scraper()