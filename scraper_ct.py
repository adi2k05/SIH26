from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import urllib.parse
import sqlite3
import random
import traceback
import re
import time
import os

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

def run_cmt_pipeline_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]

    city_map = {
        "DEL": "New Delhi", "BOM": "Mumbai", "BLR": "Bangalore", 
        "HYD": "Hyderabad", "CCU": "Kolkata", "GOI": "Goa", 
        "MAA": "Chennai", "AMD": "Ahmedabad"
    }

    print("Launching Cleartrip Pipeline Scraper (UI Filter, Scrolling, Non-Stop, Flight No & DB Writer)...")
    
    user_data_dir = os.path.join(os.getcwd(), "cleartrip_browser_profile")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            channel="chrome",
            headless=False,
            viewport={"width": 1920, "height": 1080},
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            ignore_default_args=["--enable-automation"]
        )

        try:
            for route_idx, route in enumerate(top_20_routes):
                origin, dest = route.split("-")
                
                all_done = all(is_already_scraped(route, w, "Cleartrip") for w in advance_windows)
                if all_done:
                    print(f"\n⏩ Route {route} completely skipped (already collected today). Moving immediately to next.")
                    continue

                print(f"\n==================================================")
                print(f"🛫 STARTING ROUTE [{route_idx+1}/20]: {route}")
                print(f"==================================================")
                
                scraped_any_window = False
                
                for window in advance_windows:
                    if is_already_scraped(route, window, "Cleartrip"):
                        print(f"⏩ Cleartrip: {route} | T+{window} already collected today. Skipping.")
                        continue

                    scraped_any_window = True
                    future_date_obj = datetime.now() + timedelta(days=window)
                    date_str = future_date_obj.strftime("%d/%m/%Y")
                    
                    origin_name = city_map.get(origin, origin)
                    dest_name = city_map.get(dest, dest)
                    
                    origin_encoded = urllib.parse.quote(f"{origin} - {origin_name}, IN", safe=',')
                    dest_encoded = urllib.parse.quote(f"{dest} - {dest_name}, IN", safe=',')

                    print(f"\n--- Cleartrip Scraping: {route} | T+{window} Days ({date_str}) ---")
                    
                    success = False
                    for attempt in range(1, 3):
                        page = context.pages[0] if context.pages else context.new_page()
                        
                        try:
                            url = f"https://www.cleartrip.com/flights/results?adults=1&childs=0&infants=0&class=Economy&depart_date={date_str}&from={origin}&to={dest}&intl=n&origin={origin_encoded}&destination={dest_encoded}"
                            
                            page.goto(url, wait_until="domcontentloaded", timeout=45000)
                            page.wait_for_selector('button:has-text("Book")', timeout=25000)
                            page.wait_for_timeout(2500)

                            # --- CLICK NON-STOP FILTER ON UI ---
                            print("🎯 Ticking 'Non-stop' filter on UI...")
                            try:
                                page.evaluate("""() => {
                                    let elements = Array.from(document.querySelectorAll('p, span, div'));
                                    let nonStop = elements.find(el => el.innerText && (el.innerText.trim() === 'Non Stop' || el.innerText.trim() === 'Non-stop'));
                                    if (nonStop) {
                                        // Cleartrip sidebar filters act on the parent block
                                        let clickable = nonStop.closest('div') || nonStop.parentElement;
                                        clickable.click();
                                    }
                                }""")
                                page.wait_for_timeout(3500)  # Wait for React DOM to reload with filtered results
                            except Exception:
                                pass

                            print("Scrolling to load all virtual flight cards...")
                            seen_card_signatures = set()
                            flight_records = []
                            
                            scroll_attempts = 0
                            max_scrolls = 30
                            stagnant_scrolls = 0

                            while scroll_attempts < max_scrolls:
                                raw_flight_texts = page.evaluate("""() => {
                                    const buttons = Array.from(document.querySelectorAll('button')).filter(b => b.innerText && b.innerText.includes('Book'));
                                    return buttons.map(btn => {
                                        let card = btn.closest('div[class*="flight"]') || btn.parentElement.parentElement.parentElement.parentElement;
                                        return card ? card.innerText : "";
                                    });
                                }""")

                                new_cards_found = False
                                for raw_text in raw_flight_texts:
                                    if not raw_text or len(raw_text) < 30:
                                        continue
                                    
                                    # Strict Fallback Text Filter (in case the UI click was interrupted)
                                    if "non-stop" not in raw_text.lower() and "non stop" not in raw_text.lower():
                                        continue

                                    signature = raw_text[:50].strip()
                                    if signature in seen_card_signatures:
                                        continue
                                    
                                    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
                                    price_line = next((line for line in lines if '₹' in line), None)
                                    if not price_line:
                                        continue
                                    
                                    clean_price_str = re.sub(r'[^\d.]', '', price_line)
                                    if not clean_price_str:
                                        continue
                                        
                                    try:
                                        total_fare = float(clean_price_str)
                                    except ValueError:
                                        continue
                                    
                                    if not (1500 < total_fare < 75000):
                                        continue

                                    airline_name = "Cleartrip Partner"
                                    for line in lines[:6]:
                                        if any(carrier in line for carrier in ["IndiGo", "Air India Express", "Air India", "SpiceJet", "Akasa Air", "Akasa", "Vistara"]):
                                            airline_name = line
                                            break

                                    flight_match = re.search(r'\b([A-Z0-9]{2})[-\s]?(\d{3,4})\b', raw_text, re.IGNORECASE)
                                    flight_no = f"{flight_match.group(1).upper()}-{flight_match.group(2)}" if flight_match else "CMT-Flight"

                                    time_matches = re.findall(r'\b\d{2}:\d{2}\b', raw_text)
                                    dep_time = time_matches[0] if time_matches else ""

                                    seen_card_signatures.add(signature)
                                    new_cards_found = True
                                    
                                    flight_records.append((
                                        airline_name, route, window,
                                        round(total_fare * 0.85, 2), round(total_fare * 0.15, 2),
                                        total_fare, "Cleartrip", dep_time, flight_no
                                    ))

                                if not new_cards_found:
                                    stagnant_scrolls += 1
                                    if stagnant_scrolls >= 4:
                                        break 
                                else:
                                    stagnant_scrolls = 0

                                page.mouse.move(960, 540)
                                page.mouse.wheel(0, 1200)
                                page.wait_for_timeout(1500)
                                scroll_attempts += 1

                            if flight_records:
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
                                    conn.executemany('''
                                        INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ''', flight_records)
                                    conn.commit()
                                print(f"✅ Saved {len(flight_records)} strict Non-Stop records (Attempt {attempt}).")
                                success = True
                                break
                            else:
                                raise Exception("Zero valid fare numbers parsed from card texts.")

                        except Exception as e:
                            print(f"⚠️ Cleartrip Attempt {attempt} failed: {e}")
                            if attempt == 1:
                                time.sleep(4)
                    
                    if success:
                        jitter = random.uniform(4.0, 7.0)
                        print(f"⏳ Cooling down for {round(jitter, 1)}s...")
                        time.sleep(jitter)

                if scraped_any_window:
                    route_jitter = random.uniform(8.0, 14.0)
                    print(f"\n⏳ Route complete. Cooling down for {round(route_jitter, 1)}s before next route...")
                    time.sleep(route_jitter)

        except Exception as e:
            print(f"❌ Batch Scrape failed. Exception: {e}")
            traceback.print_exc()
        finally:
            context.close()
            
        print("\n🎉 Cleartrip Pipeline Scraping Complete!")

if __name__ == "__main__":
    run_cmt_pipeline_scraper()
    os._exit(0)