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
            AND date(timestamp) = date('now')
        """, (route, window, source))
        return c.fetchone()[0] > 0

def run_airindia_express_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    city_map = {
        "DEL": "New Delhi", "BOM": "Mumbai", "BLR": "Bengaluru", 
        "HYD": "Hyderabad", "CCU": "Kolkata", "GOI": "Goa", 
        "MAA": "Chennai", "AMD": "Ahmedabad"
    }

    print("Launching Air India Express Scraper (Native UI & Anti-Bot Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])

        for route in top_20_routes:
            origin, dest = route.split("-")
            origin_city = city_map[origin]
            dest_city = city_map[dest]

            for window in advance_windows:
                if is_already_scraped(route, window, "Air India Express Direct"):
                    print(f"⏩ AI Express: {route} | T+{window} already collected today. Skipping.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                target_day = str(future_date_obj.day)
                target_month = future_date_obj.strftime("%B")
                target_year = future_date_obj.strftime("%Y")
                
                # Matches aria-labels like "15 September 2026 Tuesday ₹6109"
                date_regex = re.compile(rf"^{target_day}\s+{target_month}\s+{target_year}", re.IGNORECASE)

                print(f"\n--- AI Express Scraping: {route} | T+{window} Days ({target_day} {target_month} {target_year}) ---")

                for attempt in range(1, 3):
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        viewport={"width": 1920, "height": 1080}
                    )
                    page = context.new_page()
                    
                    try:
                        page.goto("https://www.airindiaexpress.com/", wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(4500)

                        try:
                            page.get_by_text("Accept All", exact=True).first.click(force=True, timeout=3000)
                        except Exception:
                            pass

                        # 1. Fill Origin (Keyboard Emulation to bypass dynamic locator timeouts)
                        page.locator("div").filter(has_text=re.compile(r"Flying from", re.IGNORECASE)).last.click(force=True)
                        page.wait_for_timeout(800)
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.type(origin, delay=150)
                        page.wait_for_timeout(1500)
                        page.get_by_role("button").filter(has_text=re.compile(origin_city, re.IGNORECASE)).first.click(force=True)
                        page.wait_for_timeout(1000)
                        
                        # 2. Fill Destination
                        page.locator("div").filter(has_text=re.compile(r"Flying to", re.IGNORECASE)).last.click(force=True)
                        page.wait_for_timeout(800)
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.type(dest, delay=150)
                        page.wait_for_timeout(1500)
                        page.get_by_role("button").filter(has_text=re.compile(dest_city, re.IGNORECASE)).first.click(force=True)
                        page.wait_for_timeout(1500)

                        # 3. Calendar Navigation
                        date_found = False
                        for _ in range(6):
                            target_btn = page.get_by_role("button", name=date_regex)
                            if target_btn.count() > 0 and target_btn.first.is_visible():
                                target_btn.first.click(force=True)
                                date_found = True
                                break
                                
                            # Click Next Month arrow
                            page.evaluate('''() => {
                                let rightArrows = Array.from(document.querySelectorAll('img')).filter(img => (img.getAttribute('alt') || '').toLowerCase().includes('right'));
                                if (rightArrows.length > 0) {
                                    let parent = rightArrows[0].closest('button') || rightArrows[0].closest('div');
                                    if(parent) parent.click(); else rightArrows[0].click();
                                }
                            }''')
                            page.wait_for_timeout(800)

                        if not date_found:
                            raise Exception(f"Could not find or click calendar date: {target_day} {target_month}")

                        page.wait_for_timeout(1000)
                        
                        try:
                            page.get_by_role("button", name="Confirm").first.click(timeout=3000)
                        except Exception:
                            pass

                        page.wait_for_timeout(500)
                        page.get_by_role("button", name="Search Flight").first.click(force=True)

                        # 4. Wait for Matrix and Catch Akamai Overlays
                        flights_loaded = False
                        no_flights = False
                        
                        for _ in range(30):
                            try:
                                body_text = page.locator("body").inner_text()
                                
                                if "Take a Break" in body_text or "Search after some time" in body_text:
                                    try:
                                        page.get_by_role("button", name="Ok").first.click(timeout=2000)
                                    except: pass
                                    raise Exception("Akamai Rate Limit block detected.")
                                
                                if "no flights found" in body_text.lower():
                                    no_flights = True
                                    break
                                
                                if "Departing Flights" in body_text and (body_text.count("₹") > 2 or body_text.count("Rs") > 2):
                                    flights_loaded = True
                                    break
                            except Exception as inner_e:
                                if "Akamai" in str(inner_e):
                                    raise inner_e
                                pass
                            page.wait_for_timeout(1000)

                        if no_flights:
                            print(f"ℹ️ Air India Express does not operate flights on {route} for T+{window}.")
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.execute('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time)
                                    VALUES (?, ?, ?, NULL, NULL, NULL, ?, NULL)
                                ''', ("Air India Express", route, window, "Air India Express Direct"))
                                conn.commit()
                            context.close()
                            break

                        if not flights_loaded:
                            raise Exception("Flight results failed to render.")

                        page.wait_for_timeout(2000)
                        try:
                            page.evaluate("window.scrollBy(0, 1500)")
                            page.wait_for_timeout(1000)
                        except Exception:
                            pass

                        # 5. Extract Multi-Fares
                        lines = [l.strip() for l in page.locator("body").inner_text().split('\n') if l.strip()]
                        fares = [int(re.sub(r'[^\d]', '', l)) for l in lines if ('₹' in l or 'Rs' in l) and re.sub(r'[^\d]', '', l)]
                        valid_fares = [f for f in fares if 1500 < f < 75000]

                        if valid_fares:
                            insert_payload = [
                                ("Air India Express", route, window, round(f * 0.85, 2), round(f * 0.15, 2), f, "Air India Express Direct", f"T{idx+1}") 
                                for idx, f in enumerate(valid_fares)
                            ]
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                ''', insert_payload)
                                conn.commit()
                            print(f"✅ Saved {len(valid_fares)} records (Attempt {attempt}).")
                            context.close()
                            break
                        else:
                            raise Exception("Zero valid fare numbers parsed from the results matrix.")

                    except Exception as e:
                        print(f"⚠️ Air India Express Attempt {attempt} failed: {e}")
                        context.close()
                        if attempt == 1:
                            time.sleep(6)

            time.sleep(2)

        browser.close()
        print("\nAir India Express Database Scraping Complete!")

if __name__ == "__main__":
    run_airindia_express_scraper()