from patchright.sync_api import sync_playwright
from datetime import datetime, timedelta
import re
import time

TOP_20_ROUTES = [
    "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL",
    "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL",
    "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI",
    "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM",
    "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
]

ADVANCE_WINDOWS = [1, 7, 15, 30, 45]


def extract_flights(page, origin, dest):
    cards = page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('*')).filter(
            e => e.textContent.trim() === 'Flight Details' && e.offsetParent !== null && e.children.length === 0
        );
        return btns.map(b => {
            let card = b;
            for (let i = 0; i < 12; i++) { if (card.parentElement) card = card.parentElement; }
            return card.innerText;
        });
    }''')

    results = []
    seen_flight_numbers = set()
    for raw in cards:
        lines = [l.strip() for l in raw.split('\n') if l.strip()]

        fn_idx = next((i for i, l in enumerate(lines) if re.match(r'^AI\s?\d{2,5}$', l)), None)
        if fn_idx is None:
            continue
        flight_number = lines[fn_idx]
        if flight_number in seen_flight_numbers:
            continue

        dep_time = next((l for l in lines[fn_idx:] if re.match(r'^\d{2}:\d{2}$', l)), None)
        if not dep_time:
            continue

        if "Non-stop" not in lines:
            continue  # exclude connections — a single departure_time can't represent them

        if origin not in lines or dest not in lines:
            continue  # skip alternate/nearby-airport arrivals (e.g. NMI instead of BOM)

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
            "route": f"{origin}-{dest}",
            "base_fare": round(total_fare * 0.85, 2),
            "taxes_fees": round(total_fare * 0.15, 2),
            "total_fare": total_fare,
            "ota_source": "Air India Direct",
            "departure_time": dep_time
        })

    return results


def run_airindia_scraper():
    arr = []

    print("Launching Air India Multi-Route Scraper (List Mode, all flights/day)...")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)

        for route in TOP_20_ROUTES:
            origin, dest = route.split("-")

            for window in ADVANCE_WINDOWS:
                future_date_obj = datetime.now() + timedelta(days=window)
                target_aria = f"{future_date_obj.month}/{future_date_obj.day}/{future_date_obj.year}"
                print(f"\n--- Air India Scraping: {route} | T+{window} Days ({future_date_obj.strftime('%d/%m/%Y')}) ---")

                found_any = False
                for attempt in range(1, 3):
                    # A fresh context per attempt avoids resource/connection-pool buildup
                    # from reusing one long-lived context across 100+ navigations.
                    context = browser.new_context(viewport={"width": 1920, "height": 1080})
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
                            print(f"ℹ️ Air India does not operate flights on {route} for T+{window}.")
                            arr.append({
                                "airline": "Air India",
                                "route": route,
                                "advance_window_days": window,
                                "base_fare": None,
                                "taxes_fees": None,
                                "total_fare": None,
                                "ota_source": "Air India Direct",
                                "departure_time": None
                            })
                            found_any = True
                            context.close()
                            break

                        if not flights_loaded:
                            raise Exception("Flight list never rendered.")

                        page.wait_for_timeout(1500)
                        flights = extract_flights(page, origin, dest)

                        if flights:
                            for f in flights:
                                f["advance_window_days"] = window
                            arr.extend(flights)
                            print(f"✅ Air India: {route} | T+{window} captured {len(flights)} flights (Attempt {attempt}).")
                            found_any = True
                            context.close()
                            break
                        else:
                            raise Exception("Zero valid non-stop flights parsed from card texts.")

                    except Exception as e:
                        print(f"⚠️ Air India {route} T+{window} Attempt {attempt} failed: {e}")
                        context.close()
                        if attempt == 1:
                            time.sleep(8)

                if not found_any:
                    print(f"ℹ️ Air India: {route} | T+{window} yielded no data after retries.")

                # A longer pause between combos gives Air India's backend breathing room —
                # hitting it every ~2s with minimal spacing was correlating with consecutive
                # failures that didn't reproduce in isolated, naturally-spaced-out requests.
                time.sleep(8)

        browser.close()

    print("\n==========================================")
    print("Air India In-Memory Scraping Complete!")
    print(f"Total records stored: {len(arr)}")
    print("==========================================")
    for item in arr:
        print(item)

    return arr


if __name__ == "__main__":
    run_airindia_scraper()