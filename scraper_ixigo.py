from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import sqlite3
import re
import time
import os

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

def is_already_scraped(route, window, source):
    if os.environ.get("FORCE_RESCRAPE") == "1":
        return False
    with sqlite3.connect('airfare_index.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM raw_fares 
            WHERE route = ? AND advance_window_days = ? AND ota_source = ? 
            AND date(timestamp) = date('now')
        """, (route, window, source))
        return c.fetchone()[0] > 0

def run_ixigo_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]

    print("Launching Ixigo Chrome Scraper (DB Pipeline Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        for route in top_20_routes:
            origin, dest = route.split("-")

            for window in advance_windows:
                if is_already_scraped(route, window, "Ixigo"):
                    print(f"⏩ Ixigo: {route} | T+{window} already collected today. Skipping.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d%m%Y")
                print(f"\n--- Ixigo Scraping: {route} | T+{window} Days ({future_date_obj.strftime('%d/%m/%Y')}) ---")

                for attempt in range(1, 3):
                    page = context.new_page()
                    try:
                        url = build_ixigo_url(origin, dest, date_str)
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(6000)

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
                            flight_number = lines[airline_idx + 1] if len(lines) > airline_idx + 1 else None
                            
                            if not flight_number or not re.match(r'^[A-Z0-9]{2,3}\d{2,5}$', flight_number):
                                continue
                            if flight_number in seen_flight_numbers:
                                continue  

                            if origin not in lines or dest not in lines:
                                continue  

                            price_line = next((l for l in lines if re.match(r'^₹[\d,]+$', l)), None)
                            if not price_line:
                                continue

                            total_fare = float(re.sub(r'[^\d.]', '', price_line))
                            if not (1500 < total_fare < 75000):
                                continue

                            seen_flight_numbers.add(flight_number)
                            current_batch.append((
                                normalize_airline(airline_line),
                                route,
                                window,
                                round(total_fare * 0.85, 2),
                                round(total_fare * 0.15, 2),
                                total_fare,
                                "Ixigo",
                                flight_number
                            ))

                        if current_batch:
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                ''', current_batch)
                                conn.commit()
                            print(f"✅ Ixigo T+{window}: captured {len(current_batch)} fares (Attempt {attempt}).")
                            page.close()
                            break
                        else:
                            raise Exception("Zero valid fares parsed from card texts.")

                    except Exception as e:
                        print(f"⚠️ Ixigo T+{window} Attempt {attempt} failed: {e}")
                        page.close()
                        if attempt == 1:
                            time.sleep(3)

                time.sleep(2)

        browser.close()
        print("\nIxigo Database Scraping Complete!")

if __name__ == "__main__":
    run_ixigo_scraper()