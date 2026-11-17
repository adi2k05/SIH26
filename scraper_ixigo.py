import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from datetime import datetime, timedelta
import sqlite3
import time
import os
import threading
import sys

# --- HOTFIX FOR WinError 6 ---
original_excepthook = threading.excepthook
def suppress_winerror6_excepthook(args):
    if issubclass(args.exc_type, OSError) and getattr(args.exc_value, 'winerror', None) == 6:
        pass 
    else:
        original_excepthook(args)
threading.excepthook = suppress_winerror6_excepthook

original_sys_excepthook = sys.excepthook
def suppress_winerror6_sys_excepthook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, OSError) and getattr(exc_value, 'winerror', None) == 6:
        pass
    else:
        original_sys_excepthook(exc_type, exc_value, exc_traceback)
sys.excepthook = suppress_winerror6_sys_excepthook
# -----------------------------

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

def run_ixigo_scraper():
    # --- DYNAMIC ROUTE INJECTION (BFS MODE) ---
    target_routes_env = os.environ.get("TARGET_ROUTES")
    top_20_routes = [r.strip() for r in target_routes_env.split(",")] if target_routes_env else [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    advance_windows = [1, 7, 15, 30, 45]
    
    print("Launching Ixigo Scraper (React Lazy-Load Bypass & Strict Route Filtering)...")
    
    user_data_dir = os.path.join(os.getcwd(), "ixigo_browser_profile")
    
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument(f"--user-data-dir={user_data_dir}")
    
    driver = None
    try:
        driver = uc.Chrome(options=options, use_subprocess=True)
        driver.set_page_load_timeout(60)
        
        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                if is_already_scraped(route, window, "Ixigo"):
                    print(f"⏩ Ixigo: {route} | T+{window} already collected today. Skipping.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d%m%Y")
                
                search_url = f"https://www.ixigo.com/search/result/flight?from={origin}&to={dest}&date={date_str}&adults=1&children=0&infants=0&class=e&source=Search+Form"
                
                print(f"\n--- Ixigo Scraping: {route} | T+{window} Days ({date_str}) ---")
                
                for attempt in range(1, 3):
                    try:
                        driver.get(search_url)
                        time.sleep(5) 
                        
                        print("Waiting for results to render...")
                        loaded = False
                        for _ in range(30):
                            try:
                                body_text = driver.find_element(By.TAG_NAME, "body").text
                                if "₹" in body_text or "Rs" in body_text:
                                    loaded = True
                                    break
                                if "no flights" in body_text.lower() or "sold out" in body_text.lower() or "no results" in body_text.lower():
                                    loaded = "EMPTY"
                                    break
                            except:
                                pass
                            time.sleep(1)
                        
                        if not loaded:
                            raise Exception("Timeout waiting for flights to render.")
                        
                        if loaded == "EMPTY":
                            print(f"ℹ️ Ixigo officially returned no flights for T+{window}. Logging NULL.")
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.execute('''
                                    CREATE TABLE IF NOT EXISTS raw_fares (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                        airline TEXT, route TEXT, advance_window_days INTEGER, base_fare REAL, 
                                        taxes_fees REAL, total_fare REAL, ota_source TEXT, departure_time TEXT, flight_no TEXT
                                    )
                                ''')
                                conn.execute('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                    VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?, NULL)
                                ''', ("Unknown", route, window, "Ixigo", "TBD"))
                                conn.commit()
                            break 
                        
                        print("Scrolling to load all flights...")
                        seen_flights = set()
                        route_data = []
                        
                        js_extractor = """
                        return (() => {
                            let results = [];
                            let priceElements = document.querySelectorAll('[data-testid="pricing"]');
                            
                            priceElements.forEach(priceEl => {
                                let card = priceEl.closest('div[class*="shadow-sm"], div[class*="border-"], div[class*="tile"], div[class*="card"]') || priceEl.parentElement;
                                if (!card) return;

                                let cardText = card.innerText || "";
                                let lines = cardText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);

                                let cleanPrice = parseInt((priceEl.innerText || "").replace(/[^0-9]/g, ''));
                                if (isNaN(cleanPrice) || cleanPrice < 1000) return;

                                let flightNum = "";
                                let airline = "Unknown";
                                
                                for (let i = 0; i < Math.min(10, lines.length); i++) {
                                    if (/^[A-Z0-9]{2}[\\-\\s]?\\d{3,4}/i.test(lines[i])) {
                                        flightNum = lines[i].replace(/\\s+/g, '-').toUpperCase();
                                        if (i > 0) airline = lines[i-1]; 
                                        break;
                                    }
                                }
                                
                                let depTime = "Unknown";
                                let timeNode = card.querySelector('h6[class*="text-primary"], .timeTileList h6');
                                if (timeNode && /\\d{2}:\\d{2}/.test(timeNode.innerText)) {
                                    let match = timeNode.innerText.match(/\\b(\\d{2}:\\d{2})\\b/);
                                    if (match) depTime = match[0];
                                } else {
                                    let times = cardText.match(/\\b(\\d{2}:\\d{2})\\b/g) || [];
                                    if (times.length > 0) depTime = times[0];
                                }
                                
                                if (flightNum) {
                                    results.push({ 
                                        airline: airline, 
                                        flight_number: flightNum, 
                                        departure_time: depTime, 
                                        total_fare: cleanPrice,
                                        card_text: cardText 
                                    });
                                }
                            });
                            return results;
                        })();
                        """
                        
                        scroll_attempts = 0
                        max_scrolls = 35
                        last_flight_count = 0
                        stagnant_scrolls = 0
                        
                        bad_airports = ["navi mumbai", "nmi", "(nmi)", "ghaziabad", "hindon", "hdo", "(hdo)", "noida"]
                        
                        try:
                            # Click the body so the browser is focused for the PageDown keystrokes
                            driver.find_element(By.TAG_NAME, 'body').click()
                        except:
                            pass
                        
                        while scroll_attempts < max_scrolls:
                            current_flights = driver.execute_script(js_extractor)
                            
                            for f in current_flights:
                                raw_text = f.get('card_text', '').lower()
                                
                                # --- STRICT PYTHON POST-FILTERING ---
                                if any(bad in raw_text for bad in bad_airports):
                                    continue
                                
                                has_origin = origin.lower() in raw_text
                                has_dest = dest.lower() in raw_text
                                if not (has_origin and has_dest):
                                    continue
                                
                                uniq_key = f"{f['flight_number']}_{f['departure_time']}_{f['total_fare']}"
                                if uniq_key not in seen_flights:
                                    seen_flights.add(uniq_key)
                                    base_fare = round(f['total_fare'] * 0.85, 2)
                                    taxes_fees = round(f['total_fare'] * 0.15, 2)
                                    
                                    route_data.append((
                                        f['airline'], route, window, 
                                        base_fare, taxes_fees, f['total_fare'], "Ixigo", f['departure_time'], f['flight_number']
                                    ))
                            
                            if len(seen_flights) == last_flight_count:
                                stagnant_scrolls += 1
                                if stagnant_scrolls >= 4:
                                    break 
                            else:
                                stagnant_scrolls = 0
                                
                            last_flight_count = len(seen_flights)
                            
                            # --- REACT LAZY-LOAD BYPASS SCROLLING ---
                            driver.execute_script("""
                                // 1. Fire a synthetic WheelEvent to wake up React listeners
                                window.dispatchEvent(new WheelEvent('wheel', { deltaY: 1500, bubbles: true }));
                                
                                // 2. Find the last rendered flight card and force it into view (Triggers IntersectionObserver)
                                let cards = document.querySelectorAll('[data-testid="pricing"]');
                                if (cards.length > 0) {
                                    cards[cards.length - 1].scrollIntoView({behavior: 'smooth', block: 'end'});
                                }
                                
                                // 3. Fallback native scroll
                                window.scrollBy(0, 1000);
                            """)
                            
                            try:
                                # 4. Physical PageDown keystroke
                                ActionChains(driver).send_keys(Keys.PAGE_DOWN).perform()
                            except:
                                pass
                                
                            time.sleep(1.5) # Wait for network requests to fetch next batch
                            scroll_attempts += 1
                        
                        if route_data:
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.execute('''
                                    CREATE TABLE IF NOT EXISTS raw_fares (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                        airline TEXT, route TEXT, advance_window_days INTEGER, base_fare REAL, 
                                        taxes_fees REAL, total_fare REAL, ota_source TEXT, departure_time TEXT, flight_no TEXT
                                    )
                                ''')
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', route_data)
                                conn.commit()
                                
                            print(f"✅ Saved {len(route_data)} strictly verified records (Attempt {attempt}).")
                            break 
                        else:
                            raise Exception("Zero valid flights extracted.")
                                        
                    except Exception as e:
                        print(f"⚠️ Ixigo Attempt {attempt} failed: {e}")
                        if attempt == 1:
                            time.sleep(5)
                    
                time.sleep(3)

    except Exception as e:
        print(f"❌ Critical Error: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        print("\n🎉 Ixigo Scraping Complete!")

if __name__ == "__main__":
    run_ixigo_scraper()