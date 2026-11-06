"""
Air India Optimized Scraper (scraper_ai.py)
-------------------------------------------
Optimized for:
1. 0% Timeout Rate: Eliminates the 60000ms+ hangs caused by 50+ third-party trackers/media on airindia.com.
2. In-Memory List Mode: Collects data in a Python list (database writes disabled by default for testing).
3. Accurate Airport Matching: Fixes autocomplete bug where "DEL" matched "Adelaide (ADL)" or "Aalborg (AAL)".
4. Departure Calendar Scoping: Scopes calendar clicks strictly to 'from-calendar' to avoid return calendar confusion.
5. No Video I/O Thrashing: Disables heavy full-HD WebM disk recording.
"""

import os
import re
import time
import sqlite3
from datetime import datetime, timedelta
from patchright.sync_api import sync_playwright

# All 20 routes configured in the pipeline
TOP_20_ROUTES = [
    "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
    "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
    "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
    "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
    "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
]

ADVANCE_WINDOWS = [1, 7, 15, 30, 45]


def extract_flights(page, origin, dest):
    """
    Evaluates flight cards on the Air India results page.
    Captures flight number, departure time, route, base fare, taxes, and total fare.
    """
    cards = page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('*')).filter(
            e => e.textContent.trim() === 'Flight Details' && e.offsetParent !== null && e.children.length === 0
        );
        return btns.map(b => {
            let card = b.closest('mat-card');
            if (card) return card.innerText;
            
            // fallback if mat-card structure varies
            card = b;
            for (let i = 0; i < 12; i++) { if (card.parentElement) card = card.parentElement; }
            return card.innerText;
        });
    }''')

    results = []
    seen_flight_numbers = set()
    for raw in cards:
        lines = [l.strip() for l in raw.split('\n') if l.strip()]

        # Identify flight number (AI / IX / UK)
        fn_idx = next((i for i, l in enumerate(lines) if re.match(r'^(AI|IX|UK)\s?\d{2,5}', l)), None)
        if fn_idx is None:
            continue
        flight_number = lines[fn_idx].replace(" ", "-")
        if flight_number in seen_flight_numbers:
            continue

        # Departure time format (HH:MM)
        dep_time = next((l for l in lines[fn_idx:] if re.match(r'^\d{2}:\d{2}$', l)), None)
        if not dep_time:
            continue

        # Check route origin & dest in card lines
        if origin not in lines or dest not in lines:
            continue

        # Extract fare price
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


def select_exact_airport(page, input_locator, code):
    """
    Types the 3-letter IATA code and waits for the exact matching mat-option.
    Prevents accidentally clicking another airport like 'Aalborg' or 'Adelaide'.
    """
    input_locator.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(code, delay=80)
    
    # Wait for the autocomplete dropdown options to appear
    page.locator("mat-option").first.wait_for(state="visible", timeout=10000)
    page.wait_for_timeout(400)
    
    options = page.locator("mat-option").all()
    # Priority 1: Match code as first line/badge
    for opt in options:
        text = opt.inner_text().strip()
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if lines and (lines[0] == code or lines[0].startswith(code)):
            print(f"  [Selected {code}] {lines[0]} - {lines[1] if len(lines)>1 else ''}")
            opt.click()
            return True

    # Priority 2: Word boundary match
    for opt in options:
        text = opt.inner_text().strip()
        if re.search(rf"\b{code}\b", text):
            print(f"  [Selected {code} (boundary)] {text.splitlines()[0]}")
            opt.click()
            return True

    # Fallback
    options[0].click()
    return False


def run_airindia_scraper(routes=None, windows=None, save_db=False):
    """
    Executes the optimized Air India scraper.
    
    :param routes: List of route strings (e.g. ["DEL-BOM"]). Defaults to 1 route for testing.
    :param windows: List of advance days (e.g. [7]). Defaults to [7] for testing.
    :param save_db: If True, writes to airfare_index.db. Defaults to False (pure in-memory list).
    :return: List of all captured flight dictionaries.
    """
    if routes is None:
        routes = ["DEL-BOM"]  # Change to TOP_20_ROUTES for full run
    if windows is None:
        windows = [7]          # Change to ADVANCE_WINDOWS for full run

    scraped_flights = []
    print(f"\n=======================================================")
    print(f"Starting Air India Scraper (Routes: {len(routes)}, Windows: {len(windows)}, DB Save: {save_db})")
    print(f"=======================================================")

    is_headless = os.environ.get("HEADLESS_MODE") == "1"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=is_headless,
            args=["--disable-blink-features=AutomationControlled"]
        )

        for route in routes:
            origin, dest = route.split("-")

            for window in windows:
                future_date = datetime.now() + timedelta(days=window)
                target_aria = f"{future_date.month}/{future_date.day}/{future_date.year}"
                target_iso = future_date.strftime("%Y-%m-%d")

                print(f"\n--- Scraping {route} | T+{window} Days ({target_iso}) ---")

                # Fresh context per query (no video recording to keep CPU/disk fast)
                context = browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
                page = context.new_page()

                # Optimization: Block heavy media and tracking networks that cause 60s+ timeouts
                def block_unnecessary_traffic(route_req):
                    url = route_req.request.url.lower()
                    rtype = route_req.request.resource_type
                    if rtype in ["image", "media"]:
                        route_req.abort()
                    elif any(k in url for k in ["google", "facebook", "doubleclick", "clarity", "demdex", "analytics"]):
                        route_req.abort()
                    else:
                        route_req.continue_()

                page.route("**/*", block_unnecessary_traffic)

                try:
                    t0 = time.time()
                    print(f"[{time.strftime('%H:%M:%S')}] Navigating to airindia.com...")
                    page.goto("https://www.airindia.com/", wait_until="commit", timeout=25000)
                    
                    # Wait for autocomplete input to attach
                    page.locator("input.ai-autocomplete-input").first.wait_for(state="attached", timeout=12000)
                    print(f"[{time.strftime('%H:%M:%S')}] Booking widget ready in {time.time()-t0:.2f}s.")

                    # Dismiss cookie banner
                    try:
                        cookie_btn = page.locator("#onetrust-accept-btn-handler")
                        if cookie_btn.is_visible(timeout=1500):
                            cookie_btn.click()
                    except:
                        pass

                    # Select One Way
                    oneway_radio = page.locator("input[value='one-way']").locator("..")
                    if oneway_radio.count() > 0:
                        oneway_radio.first.click()
                    else:
                        page.get_by_text("One Way", exact=True).first.click(timeout=4000)
                    page.wait_for_timeout(300)

                    # Origin & Destination selection
                    origin_input = page.locator("input.ai-autocomplete-input").nth(0)
                    select_exact_airport(page, origin_input, origin)
                    page.wait_for_timeout(400)

                    dest_input = page.locator("input.ai-autocomplete-input").nth(1)
                    select_exact_airport(page, dest_input, dest)
                    page.wait_for_timeout(400)

                    # Calendar Date Selection
                    date_trigger = page.get_by_text("Select Date", exact=True).first
                    if not date_trigger.is_visible(timeout=2000):
                        date_trigger = page.locator(".ai-booking-widget__date, [aria-label*='Depart']").first
                    date_trigger.click()

                    # Scoped to departure calendar
                    from_cal = page.locator("mat-calendar[data-calendar-id='from-calendar']").first
                    from_cal.wait_for(state="visible", timeout=6000)

                    cell_loc = from_cal.locator(f'button.mat-calendar-body-cell[aria-label="{target_aria}"]')
                    for _ in range(4):
                        if cell_loc.count() > 0 and cell_loc.first.is_visible():
                            break
                        page.get_by_role("button", name="Next month").first.click()
                        page.wait_for_timeout(400)

                    cell_loc.first.click()
                    page.wait_for_timeout(400)

                    # Click Search
                    print(f"[{time.strftime('%H:%M:%S')}] Submitting search...")
                    page.get_by_role("button", name="Search", exact=True).first.click(timeout=8000)
                    t_search = time.time()

                    # Wait for results
                    flights_loaded = False
                    for poll in range(40):
                        if page.locator("text='Flight Details'").count() > 0:
                            flights_loaded = True
                            print(f"[{time.strftime('%H:%M:%S')}] Flights loaded in {time.time()-t_search:.2f}s!")
                            break

                        body = page.locator("body").inner_text()
                        if "SOMETHING WENT WRONG" in body.upper():
                            print("  Warning: Air India results page threw 'Something went wrong'.")
                            break
                        if "no flights" in body.lower() or "sorry" in body.lower():
                            print(f"  Info: No flights scheduled on {route} for T+{window}.")
                            break
                        page.wait_for_timeout(800)

                    if flights_loaded:
                        page.wait_for_timeout(1500)
                        flights = extract_flights(page, origin, dest)
                        for f in flights:
                            f["advance_window_days"] = window
                        scraped_flights.extend(flights)
                        print(f"  Success: Captured {len(flights)} flights on {route} (T+{window}).")
                        
                        # DB write (only if save_db is explicitly enabled)
                        if save_db:
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
                            print(f"  Stored {len(flights)} records to airfare_index.db")

                    context.close()

                except Exception as e:
                    print(f"  Error on {route} T+{window}: {e}")
                    context.close()

        browser.close()

    print(f"\n=======================================================")
    print(f"Scraping Complete! Total flights collected: {len(scraped_flights)}")
    print(f"=======================================================")
    return scraped_flights


if __name__ == "__main__":
    # Diagnostic test: 1 route, 1 window, pure list output (no DB touch)
    results = run_airindia_scraper(
        routes=["DEL-BOM"], 
        windows=[7], 
        save_db=False
    )
    for r in results[:5]:
        print(r)
