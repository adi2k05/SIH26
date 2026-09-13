from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import re
import time

KNOWN_AIRLINES = [
    "IndiGo", "Air-India Express", "Air India Express", "Air India",
    "SpiceJet", "Akasa Air", "Vistara", "Alliance Air", "Go First", "GoAir"
]


def normalize_airline(name):
    if "air-india express" in name.lower() or "air india express" in name.lower():
        return "Air India Express"
    return name


def build_ixigo_url(origin, dest, date_str):
    return (
        f"https://www.ixigo.com/search/result/flight?"
        f"from={origin}&to={dest}&date={date_str}"
        f"&adults=1&children=0&infants=0&class=e&source=Search+Form"
    )


def run_ixigo_scraper():
    origin = "DEL"
    dest = "BOM"
    advance_windows = [7, 1, 15, 45]

    arr = []

    print("Launching Ixigo Chrome Scraper (List Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        for window in advance_windows:
            future_date_obj = datetime.now() + timedelta(days=window)
            date_str = future_date_obj.strftime("%d%m%Y")
            print(f"\n--- Ixigo Scraping: {origin}-{dest} | T+{window} Days ({future_date_obj.strftime('%d/%m/%Y')}) ---")

            for attempt in range(1, 3):
                page = context.new_page()
                try:
                    url = build_ixigo_url(origin, dest, date_str)
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(6000)

                    # Remove the exit-intent overlay that blocks interaction/rendering checks
                    page.evaluate('''() => {
                        ["intentOpacityDiv", "intentPreview"].forEach(id => {
                            const el = document.getElementById(id);
                            if (el) el.remove();
                        });
                    }''')

                    flights_loaded = False
                    for _ in range(20):
                        if page.locator('button:has-text("Book"), div:has-text("Book")').count() > 0:
                            flights_loaded = True
                            break
                        page.wait_for_timeout(1000)

                    if not flights_loaded:
                        raise Exception("Flight cards did not render in DOM.")

                    # The results list lazy-renders as you scroll; load more of it before extracting
                    for _ in range(6):
                        page.mouse.wheel(0, 1500)
                        page.wait_for_timeout(800)

                    raw_cards = page.evaluate('''() => {
                        const buttons = Array.from(document.querySelectorAll('button, div')).filter(
                            e => e.textContent.trim() === 'Book' && e.offsetParent !== null
                        );
                        return buttons.map(b => {
                            let card = b;
                            for (let i = 0; i < 3; i++) { if (card.parentElement) card = card.parentElement; }
                            return card.innerText;
                        });
                    }''')

                    current_batch = []
                    seen_flight_numbers = set()
                    for raw_text in raw_cards:
                        if not raw_text:
                            continue
                        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                        if not lines:
                            continue

                        airline_idx = next((i for i, l in enumerate(lines[:2]) if any(a.lower() in l.lower() for a in KNOWN_AIRLINES)), None)
                        if airline_idx is None:
                            continue
                        airline_line = lines[airline_idx]

                        # The line right after the airline name is the flight number (e.g. AI2945, 6E5096)
                        flight_number = lines[airline_idx + 1] if len(lines) > airline_idx + 1 else None
                        if not flight_number or not re.match(r'^[A-Z0-9]{2,3}\d{2,5}$', flight_number):
                            continue
                        if flight_number in seen_flight_numbers:
                            continue  # the lazy-loaded list re-renders some rows more than once

                        if origin not in lines or dest not in lines:
                            continue  # skip alternate/nearby-airport results

                        price_line = next((l for l in lines if re.match(r'^₹[\d,]+$', l)), None)
                        if not price_line:
                            continue

                        total_fare = float(re.sub(r'[^\d.]', '', price_line))
                        if not (1500 < total_fare < 75000):
                            continue

                        seen_flight_numbers.add(flight_number)
                        current_batch.append({
                            "airline": normalize_airline(airline_line),
                            "route": f"{origin}-{dest}",
                            "advance_window_days": window,
                            "base_fare": round(total_fare * 0.85, 2),
                            "taxes_fees": round(total_fare * 0.15, 2),
                            "total_fare": total_fare,
                            "ota_source": "Ixigo"
                        })

                    if current_batch:
                        arr.extend(current_batch)
                        print(f"✅ Ixigo T+{window}: captured {len(current_batch)} fares (Attempt {attempt}).")
                        page.close()
                        break
                    else:
                        raise Exception("Zero valid DEL-BOM fares parsed from card texts.")

                except Exception as e:
                    print(f"⚠️ Ixigo T+{window} Attempt {attempt} failed: {e}")
                    page.close()
                    if attempt == 1:
                        time.sleep(3)

            time.sleep(2)

        browser.close()

    print("\n==========================================")
    print("Ixigo In-Memory Scraping Complete!")
    print(f"Total records stored: {len(arr)}")
    print("==========================================")
    for item in arr:
        print(item)

    return arr


if __name__ == "__main__":
    run_ixigo_scraper()
