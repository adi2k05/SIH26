import sqlite3
from patchright.sync_api import sync_playwright
from datetime import datetime, timedelta
import time
import os
import re
import random

def is_already_scraped(route, window, source):
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

def clear_browser_data(page):
    try:
        client = page.context.new_cdp_session(page)
        client.send('Network.clearBrowserCookies')
        client.send('Network.clearBrowserCache')
        page.evaluate("window.localStorage.clear(); window.sessionStorage.clear();")
        print("🧹 CDP: Cleared poisoned browser session storage and Akamai cookies.", flush=True)
    except Exception as e:
        pass

def click_red_zone_while_loading(page, max_timeout=35.0):
    """
    Simulates authentic human clicking inside the red scribble zone on the left margin.
    Outputs terminal logs on EVERY click showing coordinates, hold time, delay, and page state.
    """
    start_time = time.time()
    click_count = 0
    
    viewport = page.viewport_size or {"width": 1920, "height": 1080}
    w, h = viewport["width"], viewport["height"]
    
    # Red scribble zone coordinates on the left margin
    x_min, x_max = int(w * 0.03), int(w * 0.16)
    y_min, y_max = int(h * 0.20), int(h * 0.80)

    print(f"🖱️ [Red-Zone Clicker] Started! Zone bounds: X[{x_min}..{x_max}], Y[{y_min}..{y_max}] (Viewport: {w}x{h})", flush=True)

    # Initial position in red zone
    curr_x = random.randint(x_min, x_max)
    curr_y = random.randint(y_min, y_max)
    try:
        page.mouse.move(curr_x, curr_y)
    except Exception:
        pass

    while time.time() - start_time < max_timeout:
        try:
            txt = page.evaluate("() => document.body ? document.body.innerText : ''")
        except Exception:
            txt = ""

        # 1. Real flight data loaded
        if "Flight Details" in txt or "Departing Flights" in txt:
            elapsed = time.time() - start_time
            print(f"🎉 Flights rendered! (Delivered {click_count} clicks in red zone in {elapsed:.2f}s)", flush=True)
            return "SUCCESS"

        # 2. Officially no flights
        if "We couldn't find any flights" in txt or "No flights scheduled" in txt:
            elapsed = time.time() - start_time
            print(f"ℹ️ 'No flights' detected after {click_count} clicks in {elapsed:.2f}s.", flush=True)
            return "NO_FLIGHTS"

        # 3. WAF Take a Break screen
        if "Take a Break" in txt or "Search after some time" in txt:
            elapsed = time.time() - start_time
            print(f"🛡️ WAF 'Take a Break' detected on page after {click_count} clicks in {elapsed:.2f}s!", flush=True)
            return "WAF_BLOCKED"

        # Natural human drift: smooth movement between nearby points in the red zone
        drift_x = random.randint(-25, 25)
        drift_y = random.randint(-45, 45)
        target_x = max(x_min, min(x_max, curr_x + drift_x))
        target_y = max(y_min, min(y_max, curr_y + drift_y))

        # Interpolate mouse movement to generate authentic mousemove telemetry
        steps = random.randint(3, 5)
        for s in range(1, steps + 1):
            ix = curr_x + (target_x - curr_x) * (s / steps)
            iy = curr_y + (target_y - curr_y) * (s / steps)
            try:
                page.mouse.move(ix, iy)
            except Exception:
                pass
            time.sleep(random.uniform(0.008, 0.014))

        curr_x, curr_y = int(target_x), int(target_y)

        # Human click with natural hold duration
        hold_duration = random.uniform(0.05, 0.09)
        delay_duration = random.uniform(0.16, 0.28)

        try:
            page.mouse.down()
            time.sleep(hold_duration)
            page.mouse.up()
            click_count += 1
        except Exception:
            pass

        # Terminal output for EVERY click with coordinates and timing
        elapsed_now = time.time() - start_time
        hold_ms = int(hold_duration * 1000)
        delay_ms = int(delay_duration * 1000)
        print(f"  🖱️ [Click #{click_count:02d} | +{elapsed_now:.2f}s] Coords: ({curr_x}, {curr_y}) | Hold: {hold_ms}ms | Next Delay: {delay_ms}ms | State: SKELETAL_LOADING", flush=True)

        # Human tapping cadence between clicks
        time.sleep(delay_duration)

    print(f"⚠️ [Red-Zone Clicker] Timed out after {max_timeout}s.", flush=True)
    return "TIMEOUT"

def extract_flights(page, origin, dest):
    results = []
    seen_flight_numbers = set()
    
    page.wait_for_timeout(1000)
    text = page.evaluate("() => document.body.innerText")
    
    if "Nearby Airports" in text:
        text = text.split("Nearby Airports")[0]
        
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    for i, line in enumerate(lines):
        if "Flight Details" in line:
            flight_num_line = lines[i-1]
            if not re.match(r'^(IX|I5|AI)\s?\d{2,5}', flight_num_line):
                continue
                
            flight_number = flight_num_line.replace(" ", "-")
            if flight_number in seen_flight_numbers:
                continue
                
            times = [lines[j] for j in range(max(0, i-8), i) if re.match(r'^\d{2}:\d{2}$', lines[j])]
            if not times:
                continue
            dep_time = times[0]
            
            price_line = None
            for j in range(i+1, min(i+6, len(lines))):
                if '₹' in lines[j] or 'INR' in lines[j] or re.match(r'^[\d,]+$', lines[j].replace('₹','').strip()):
                    price_line = lines[j]
                    break
                    
            if not price_line:
                continue
                
            try:
                total_fare = float(re.sub(r'[^\d.]', '', price_line))
                if not (1500 < total_fare < 75000):
                    continue
            except:
                continue
                
            seen_flight_numbers.add(flight_number)
            results.append({
                "airline": "Air India Express",
                "flight_number": flight_number,
                "route": f"{origin}-{dest}",
                "base_fare": round(total_fare * 0.85, 2),
                "taxes_fees": round(total_fare * 0.15, 2),
                "total_fare": total_fare,
                "ota_source": "Air India Express Direct",
                "departure_time": dep_time
            })
            
    return results

def run_airindia_express_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]

    print("Launching Native Air India Express (Direct URL + Live Click Telemetry)...", flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        
        for route in top_20_routes:
            origin, dest = route.split("-")

            for window in advance_windows:
                if is_already_scraped(route, window, "Air India Express Direct"):
                    print(f"Skipping Air India Express: {route} | T+{window} already collected today.", flush=True)
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                target_iso = future_date_obj.strftime("%Y-%m-%d")

                print(f"\n--- Air India Express Scraping: {route} | T+{window} Days ({target_iso}) ---", flush=True)

                for attempt in range(1, 3):
                    context = browser.new_context(viewport={"width": 1920, "height": 1080})
                    page = context.new_page()

                    try:
                        # Step 1: Prime cookies on homepage
                        page.goto("https://www.airindiaexpress.com/", wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(2500)
                        
                        # Step 2: Direct URL Injection (wait_until="commit" so clicks start immediately as skeleton paints)
                        search_url = f"https://www.airindiaexpress.com/flight-availability?/{origin}/{dest}/{target_iso}/N/1/0/0/0/0/0/0/O/N/INR/ST/0"
                        print(f"🔗 Navigating directly to search URL...", flush=True)
                        page.goto(search_url, wait_until="commit", timeout=60000)
                        
                        # Step 3: CONTINUOUS RED-ZONE CLICKING WHILE SKELETON LOADS
                        result_state = click_red_zone_while_loading(page, max_timeout=35.0)
                        page.wait_for_timeout(800)
                        text = page.evaluate("() => document.body ? document.body.innerText : ''")

                        # Step 4: INSTANT WAF DETECTION & COOL DOWN (Avoid spamming rapid reloads)
                        if result_state == "WAF_BLOCKED" or "Take a Break" in text or "Search after some time" in text:
                            print("🛡️ WAF Rate Limit detected ('Take a Break')! Purging CDP and resting 16s to reset Akamai velocity...", flush=True)
                            clear_browser_data(page)
                            time.sleep(16)  # Let Akamai sliding-window burst counter expire
                            
                            # Single clean reload with active red-zone clicks
                            print("🔄 Reloading search after cooldown with active red clicks...", flush=True)
                            page.reload(wait_until="commit")
                            reload_state = click_red_zone_while_loading(page, max_timeout=25.0)
                            page.wait_for_timeout(800)
                            text = page.evaluate("() => document.body ? document.body.innerText : ''")
                            if reload_state != "SUCCESS" and ("Take a Break" in text or "Search after some time" in text):
                                raise Exception("WAF Rate Limit Block")

                        if "We couldn't find any flights" in text:
                            print(f"Info: Air India Express does not operate flights on {route} for T+{window}.", flush=True)
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.execute('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                    VALUES (?, ?, ?, NULL, NULL, NULL, ?, NULL, NULL)
                                ''', ("Air India Express", route, window, "Air India Express Direct"))
                                conn.commit()
                            context.close()
                            break

                        # Step 5: Extract
                        flights = extract_flights(page, origin, dest)

                        if flights:
                            print(f"✅ Success: Air India Express {route} | T+{window} captured {len(flights)} flights (Attempt {attempt}).", flush=True)
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.execute('''
                                    CREATE TABLE IF NOT EXISTS raw_fares (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                        airline TEXT, route TEXT, advance_window_days INTEGER, base_fare REAL, 
                                        taxes_fees REAL, total_fare REAL, ota_source TEXT, departure_time TEXT, flight_no TEXT
                                    )
                                ''')
                                for f in flights:
                                    conn.execute('''
                                        INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ''', (f['airline'], f['route'], window, f['base_fare'], f['taxes_fees'], f['total_fare'], f['ota_source'], f['departure_time'], f['flight_number']))
                                conn.commit()
                            context.close()
                            break
                        else:
                            raise Exception("Zero valid flights parsed.")

                    except Exception as e:
                        print(f"⚠️ Warning: Air India Express {route} T+{window} Attempt {attempt} failed: {e}", flush=True)
                        context.close()
                        if "WAF Rate Limit Block" in str(e):
                            time.sleep(14)
                        elif attempt == 1:
                            time.sleep(4)

                # Step 6: Human inter-window pause (3.5s - 5.0s) so queries aren't fired with 0ms gap
                print("⏳ Inter-window pause (4s)...", flush=True)
                time.sleep(random.uniform(3.5, 5.0))

        browser.close()
        print("\n🎉 Air India Express Database Scraping Complete!", flush=True)

if __name__ == "__main__":
    run_airindia_express_scraper()
