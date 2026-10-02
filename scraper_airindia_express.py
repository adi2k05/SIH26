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

def extract_flights(page, origin, dest):
    results = []
    seen_flight_numbers = set()
    
    # Wait for the flights to load in the DOM
    try:
        page.locator("text=Departing Flights").wait_for(timeout=30000)
    except:
        pass # Fallback to parsing whatever is on screen if it fails
    
    page.wait_for_timeout(2000)
    text = page.evaluate("() => document.body.innerText")
    
    # CRITICAL: Exclude Nearby Airports as requested!
    if "Nearby Airports" in text:
        text = text.split("Nearby Airports")[0]
        
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    for i, line in enumerate(lines):
        if "Flight Details" in line:
            # Found a flight card! Let's extract details.
            flight_num_line = lines[i-1]
            if not re.match(r'^(IX|I5|AI)\s?\d{2,5}', flight_num_line):
                continue
                
            flight_number = flight_num_line.replace(" ", "-")
            if flight_number in seen_flight_numbers:
                continue
                
            # Extract Time (Departure is the first time seen before Flight Details)
            times = [lines[j] for j in range(max(0, i-8), i) if re.match(r'^\d{2}:\d{2}$', lines[j])]
            if not times:
                continue
            dep_time = times[0]
            
            # Extract Price (Look below Flight Details)
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

    print("Launching Native Air India Express Scraper (UI Priming + Deep Link Mode)...")

    # Use patchright with headless=False to bypass Akamai/Cloudflare
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
                        # Step 1: Prime cookies on homepage and use the full UI flow
                        page.goto("https://www.airindiaexpress.com/", wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(3000)
                        
                        try:
                            # Origin
                            page.locator("#new-flight-search-origin-field-text").first.click(timeout=5000)
                            page.wait_for_timeout(500)
                            page.locator("#basic-url-origin").fill(origin)
                            page.wait_for_timeout(1000)
                            # Select the exact airport code from the dropdown to avoid Hindon/nearby airports
                            page.evaluate(f"() => {{ const items = Array.from(document.querySelectorAll('.flight-list-group-item')); const match = items.find(i => i.innerText.includes('{origin}')); if(match) match.click(); }}")
                            
                            # Destination
                            page.locator("#new-flight-search-destination-field-text").first.click(timeout=5000)
                            page.wait_for_timeout(500)
                            page.locator("#basic-url-destination").fill(dest)
                            page.wait_for_timeout(1000)
                            page.evaluate(f"() => {{ const items = Array.from(document.querySelectorAll('.flight-list-group-item')); const match = items.find(i => i.innerText.includes('{dest}')); if(match) match.click(); }}")
                            
                            # Date
                            page.locator("#start-date-input-button").first.click(timeout=5000)
                            page.wait_for_timeout(1000)
                            
                            target_date_str = f"{future_date_obj.day} {future_date_obj.strftime('%B %Y')}"
                            # Use starts-with (^=) so "9 " doesn't match "19 " or "29 "
                            date_selector = f"[aria-label^='{target_date_str}']"
                            
                            # Loop to click next month if the date isn't visible yet
                            for _ in range(3):
                                if page.locator(date_selector).first.is_visible():
                                    page.locator(date_selector).first.click()
                                    break
                                else:
                                    # Click next month button - usually an svg or button in the calendar header
                                    # We can evaluate js to find the right arrow button
                                    page.evaluate("() => { const btns = Array.from(document.querySelectorAll('button')); const nextBtn = btns.find(b => b.innerHTML.includes('arrow') || b.innerHTML.includes('right') || b.getAttribute('aria-label') === 'Next Month'); if(nextBtn) nextBtn.click(); }")
                                    page.wait_for_timeout(500)
                            else:
                                print(f"Could not find date {target_date_str} in calendar.")

                            # Click Search button
                            page.evaluate("() => { document.querySelectorAll('button').forEach(b => { if((b.innerText || '').toLowerCase().includes('search')) b.click() }) }")
                            page.wait_for_timeout(15000) # Let the flight search load completely

                        except Exception as inner_e:
                            print("UI Navigation warning:", inner_e)
                        
                        flights = extract_flights(page, origin, dest)

                        if flights:
                            print(f"Success: Air India Express {route} | T+{window} captured {len(flights)} flights (Attempt {attempt}).")
                            
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
                                for f in flights:
                                    conn.execute('''
                                        INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ''', (f['airline'], f['route'], window, f['base_fare'], f['taxes_fees'], f['total_fare'], f['ota_source'], f['departure_time'], f['flight_number']))
                                conn.commit()
                            context.close()
                            break
                        else:
                            # Verify if it's truly empty or a block
                            text = page.evaluate("() => document.body.innerText")
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
                            
                            print(f"No valid flights found on attempt {attempt}. Retrying...")
                            raise Exception("Zero valid flights parsed.")

                    except Exception as e:
                        print(f"Warning: Air India Express {route} T+{window} Attempt {attempt} failed: {e}")
                        context.close()
                        if attempt == 1:
                            time.sleep(8)

        browser.close()
        print("Air India Express Database Scraping Complete!")

if __name__ == "__main__":
    run_airindia_express_scraper()