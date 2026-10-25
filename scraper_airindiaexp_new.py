import sqlite3
from patchright.sync_api import sync_playwright
from datetime import datetime, timedelta
import time
import os
import re

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
        print("🧹 CDP: Cleared poisoned browser session storage and Akamai cookies.")
    except Exception as e:
        pass

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

    print("Launching Native Air India Express (Direct URL + Dynamic WAF Purge/Refresh)...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        
        for route in top_20_routes:
            origin, dest = route.split("-")

            for window in advance_windows:
                if is_already_scraped(route, window, "Air India Express Direct"):
                    print(f"Skipping Air India Express: {route} | T+{window} already collected today.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                target_iso = future_date_obj.strftime("%Y-%m-%d")

                print(f"--- Air India Express Scraping: {route} | T+{window} Days ({target_iso}) ---")

                for attempt in range(1, 3):
                    context = browser.new_context(viewport={"width": 1920, "height": 1080})
                    page = context.new_page()

                    try:
                        # Step 1: Prime cookies on homepage
                        page.goto("https://www.airindiaexpress.com/", wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(3000)
                        
                        # Step 2: Direct URL Injection
                        search_url = f"https://www.airindiaexpress.com/flight-availability?/{origin}/{dest}/{target_iso}/N/1/0/0/0/0/0/0/O/N/INR/ST/0"
                        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                        
                        # Step 3: DYNAMIC WAIT - Eliminates the 15-second hang
                        try:
                            page.wait_for_function("""() => {
                                let txt = document.body.innerText;
                                return txt.includes('Departing Flights') || 
                                       txt.includes('Take a Break') || 
                                       txt.includes('Search after some time') || 
                                       txt.includes('We couldn\\'t find any flights');
                            }""", timeout=25000)
                        except:
                            pass
                            
                        page.wait_for_timeout(1500)
                        text = page.evaluate("() => document.body.innerText")

                        # Step 4: INSTANT WAF DETECTION & RAPID REFRESH BYPASS
                        if "Take a Break" in text or "Search after some time" in text:
                            print("🛡️ WAF Rate Limit detected ('Take a Break')! Engaging CDP purge and rapid reload...")
                            clear_browser_data(page)
                            
                            bypass_success = False
                            for refresh_count in range(1, 4):
                                print(f"🔄 Rapid reload bypass attempt {refresh_count}...")
                                page.reload(wait_until="domcontentloaded")
                                page.wait_for_timeout(4500)
                                text = page.evaluate("() => document.body.innerText")
                                if "Departing Flights" in text and "Take a Break" not in text:
                                    bypass_success = True
                                    break
                                    
                            if not bypass_success:
                                raise Exception("WAF Rate Limit Block - Rapid Bypass Failed")

                        if "We couldn't find any flights" in text:
                            print(f"Info: Air India Express does not operate flights on {route} for T+{window}.")
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
                            print(f"✅ Success: Air India Express {route} | T+{window} captured {len(flights)} flights (Attempt {attempt}).")
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
                        print(f"⚠️ Warning: Air India Express {route} T+{window} Attempt {attempt} failed: {e}")
                        context.close()
                        if "WAF Rate Limit Block" in str(e):
                            time.sleep(12)
                        elif attempt == 1:
                            time.sleep(5)

        browser.close()
        print("\n🎉 Air India Express Database Scraping Complete!")

if __name__ == "__main__":
    run_airindia_express_scraper()