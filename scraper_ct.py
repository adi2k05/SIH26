from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import sqlite3
import re
import time
import os

def is_already_scraped(route, window, source):
    if os.environ.get("FORCE_RESCRAPE") == "1":
        return False
    with sqlite3.connect('airfare_index.db') as conn:
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM raw_fares 
            WHERE route = ? AND advance_window_days = ? AND ota_source = ? 
            AND date(datetime(timestamp, '+5 hours', '+30 minutes')) = date(datetime('now', '+5 hours', '+30 minutes'))
        """, (route, window, source))
        return c.fetchone()[0] > 0

def run_cmt_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]

    print("Launching Cleartrip Multi-Route Scraper (Database Write Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(
            headless=False, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                if is_already_scraped(route, window, "Cleartrip"):
                    print(f"⏩ Cleartrip: {route} | T+{window} already collected today. Skipping.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d-%m-%Y")
                print(f"\n--- Cleartrip Scraping: {route} | T+{window} Days ({date_str}) ---")
                
                for attempt in range(1, 3):
                    page = context.new_page()
                    try:
                        url = f"https://www.cleartrip.com/flights/results?adults=1&childs=0&infants=0&class=Economy&depart_date={date_str}&from={origin}&to={dest}&intl=n"
                        
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_selector('button:has-text("Book")', timeout=25000)
                        
                        page.wait_for_timeout(2000)
                        page.evaluate("window.scrollBy(0, 1000);")
                        page.wait_for_timeout(2000)

                        raw_flight_texts = page.evaluate('''() => {
                            const buttons = Array.from(document.querySelectorAll('button')).filter(b => b.innerText.includes('Book'));
                            return buttons.map(btn => {
                                let card = btn.parentElement.parentElement.parentElement.parentElement;
                                return card ? card.innerText : "";
                            });
                        }''')

                        current_batch = []
                        for raw_text in raw_flight_texts:
                            if not raw_text:
                                continue
                            
                            lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
                            price_line = next((line for line in lines if '₹' in line), None)
                            if not price_line:
                                continue
                            
                            clean_price_str = re.sub(r'[^\d.]', '', price_line)
                            if not clean_price_str:
                                continue
                                
                            total_fare = float(clean_price_str)
                            
                            if not (1500 < total_fare < 75000):
                                continue

                            airline_name = "Cleartrip Partner"
                            for line in lines[:6]:
                                if any(carrier in line for carrier in ["IndiGo", "Air India Express", "Air India", "SpiceJet", "Akasa Air", "Akasa", "Vistara"]):
                                    airline_name = line
                                    break

                          # Structure formatted for executemany tuple mapping
                            current_batch.append((
                                airline_name,
                                route,
                                window,
                                round(total_fare * 0.85, 2),
                                round(total_fare * 0.15, 2),
                                total_fare,
                                "Cleartrip",
                                f"T{len(current_batch)+1}"
                            ))

                        if current_batch:
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                ''', current_batch)
                                conn.commit()
                            print(f"✅ Saved {len(current_batch)} records (Attempt {attempt}).")
                            page.close()
                            break
                        else:
                            raise Exception("Zero valid fare numbers parsed from card texts.")

                    except Exception as e:
                        print(f"⚠️ Cleartrip Attempt {attempt} failed: {e}")
                        page.close()
                        if attempt == 1:
                            time.sleep(3)
                
                time.sleep(1.5)

        browser.close()
        print("\nCleartrip Database Scraping Complete!")

if __name__ == "__main__":
    run_cmt_scraper()