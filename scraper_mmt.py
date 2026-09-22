import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from datetime import datetime, timedelta
import sqlite3
import random
import time
import traceback
import sys
import os
import threading

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

def dismiss_overlays(driver):
    """Safely cleans up any blocking modals or popups if they exist."""
    try:
        driver.execute_script("""
            let modals = document.querySelectorAll('div[data-cy="outsideModal"], .imageSliderModal, .loginModal, .overlay, .commonModal__close');
            modals.forEach(m => m.remove());
            document.body.style.overflow = 'auto';
        """)
    except:
        pass

def check_for_block(driver):
    """Detects if MMT WAF has thrown the Network Problem firewall page."""
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "network problem" in body_text or "unable to connect to our systems" in body_text:
            return True
    except:
        pass
    return False

def perform_ui_warmup(driver, wait, origin, dest, aria_date_str):
    print("Performing UI Warmup (Bypassing Network Block)...")
    driver.get("https://www.makemytrip.com/")
    time.sleep(3)
    
    if check_for_block(driver):
        raise Exception("WAF Block (Network Problem) triggered on homepage warmup.")
    
    # Non-blocking 6-7 second modal check window
    print("Checking for initial dynamic promo modal (up to 7s)...")
    modal_start = time.time()
    while time.time() - modal_start < 7.0:
        try:
            close_btn = driver.find_element(By.CSS_SELECTOR, 'span[data-cy="closeModal"], .commonModal__close')
            if close_btn.is_displayed():
                try:
                    close_btn.click()
                except:
                    driver.execute_script("arguments[0].click();", close_btn)
                print("✅ Modal closed.")
                break
        except:
            pass
        time.sleep(0.5)
        
    dismiss_overlays(driver)
    time.sleep(1)

    # 1. Select 'From' City
    print("Selecting departure city...")
    from_label = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'label[for="fromCity"]')))
    ActionChains(driver).move_to_element(from_label).click().perform()
    time.sleep(1.5)
    
    from_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input.react-autosuggest__input')))
    from_input.send_keys(origin)
    time.sleep(2.5) 
    
    if not driver.execute_script("let opt = document.querySelector('li[role=\"option\"]'); if(opt) { opt.click(); return true; } return false;"):
        raise Exception(f"No suggestions loaded for origin {origin}")
    time.sleep(1.5)

    # 2. Select 'To' City
    print("Selecting destination city...")
    try:
        to_input = driver.find_element(By.CSS_SELECTOR, 'input.react-autosuggest__input')
        if not to_input.is_displayed():
            raise Exception("Hidden")
    except:
        to_label = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'label[for="toCity"]')))
        ActionChains(driver).move_to_element(to_label).click().perform()
        time.sleep(1.5)
        to_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input.react-autosuggest__input')))
    
    to_input.send_keys(dest)
    time.sleep(2.5)
    
    if not driver.execute_script("let opt = document.querySelector('li[role=\"option\"]'); if(opt) { opt.click(); return true; } return false;"):
        raise Exception(f"No suggestions loaded for destination {dest}")
    time.sleep(1.5)

    # 3. Pick Target Date
    print(f"Selecting date: {aria_date_str}...")
    js_click_date = f"""
        let cell = document.querySelector('div.DayPicker-Day[aria-label="{aria_date_str}"]');
        if (cell) {{ cell.click(); return true; }}
        return false;
    """
    if not driver.execute_script(js_click_date):
        departure_label = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'label[for="departure"]')))
        ActionChains(driver).move_to_element(departure_label).click().perform()
        time.sleep(1.5)
        
        for _ in range(3):
            if driver.execute_script(js_click_date): break
            driver.execute_script("let nextBtn = document.querySelector('span[aria-label=\"Next Month\"]'); if (nextBtn) nextBtn.click();")
            time.sleep(1)
            
    time.sleep(1.5)

    # 4. Search
    print("Submitting search...")
    search_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.widgetSearchBtn, p[data-cy="submit"] a')))
    ActionChains(driver).move_to_element(search_btn).click().perform()


def run_mmt_multi_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]

    print("Launching MakeMyTrip Pipeline Scraper (Anti-WAF Persistent Profile Mode)...")
    user_data_dir = os.path.join(os.getcwd(), "mmt_browser_profile")

    for route_idx, route in enumerate(top_20_routes):
        origin, dest = route.split("-")
        
        # Check if all windows are already scraped before spinning up browser
        all_done = all(is_already_scraped(route, w, "MakeMyTrip") for w in advance_windows)
        if all_done:
            print(f"\n⏩ Route {route} completely skipped (already collected today). Moving immediately to next.")
            continue

        print(f"\n==================================================")
        print(f"🛫 STARTING ROUTE [{route_idx+1}/20]: {route}")
        print(f"==================================================")
        
        driver = None
        try:
            options = uc.ChromeOptions()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--start-maximized")
            options.add_argument(f"--user-data-dir={user_data_dir}")
            
            options.add_argument("--disable-background-timer-throttling")
            options.add_argument("--disable-backgrounding-occluded-windows")
            options.add_argument("--disable-renderer-backgrounding")
            
            driver = uc.Chrome(options=options, use_subprocess=True)
            wait = WebDriverWait(driver, 35)
            
            session_warmed_up = False
            scraped_any_window = False

            for window in advance_windows:
                if is_already_scraped(route, window, "MakeMyTrip"):
                    print(f"⏩ MMT: {route} | T+{window} already collected today. Skipping.")
                    continue

                scraped_any_window = True
                target_date = datetime.now() + timedelta(days=window)
                aria_date_str = target_date.strftime("%a %b %d %Y")
                url_date = target_date.strftime("%d/%m/%Y")
                
                print(f"\n--- MMT Scraping: {route} | T+{window} Days ({url_date}) ---")
                
                success = False
                for attempt in range(1, 3):
                    try:
                        if not session_warmed_up:
                            perform_ui_warmup(driver, wait, origin, dest, aria_date_str)
                            session_warmed_up = True
                        else:
                            direct_url = f"https://www.makemytrip.com/flight/search?itinerary={origin}-{dest}-{url_date}&tripType=O&paxType=A-1_C-0_I-0&intl=false&cabinClass=E&lang=eng"
                            driver.get(direct_url)
                            time.sleep(4)
                            
                        if check_for_block(driver):
                            raise Exception("WAF Block (Network Problem) triggered on search URL.")
                            
                        dismiss_overlays(driver)
                        print("Waiting for flight cards to render...")
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".listingCard, .listingCardWrap, div[class*='listingCard']")))
                        time.sleep(2)

                        js_extract = f"""
                            let results = [];
                            let cards = document.querySelectorAll('.listingCard, .listingCardWrap, div[class*="listingCard"]');
                            
                            cards.forEach(card => {{
                                let lines = (card.innerText || "").split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                                
                                let hasOrigin = lines.some(l => new RegExp("\\\\b{origin}\\\\b").test(l));
                                let hasDest = lines.some(l => new RegExp("\\\\b{dest}\\\\b").test(l));
                                if (!hasOrigin || !hasDest) return;
                                
                                let priceLine = lines.find(l => (l.includes('₹') || l.includes('Rs')) && /\\d/.test(l));
                                if (!priceLine) return;
                                
                                let priceMatch = priceLine.match(/[₹|Rs]\\s*([\\d,]+)/);
                                if (!priceMatch) return;
                                
                                let cleanPrice = parseInt(priceMatch[1].replace(/,/g, ''));
                                if (isNaN(cleanPrice) || cleanPrice < 1000) return;
                                
                                let flightNum = "";
                                let airline = "Unknown";
                                
                                for (let i = 0; i < Math.min(10, lines.length); i++) {{
                                    if (/^[A-Z0-9]{{2}}[\\-\\s]?\\d{{3,4}}/i.test(lines[i])) {{
                                        flightNum = lines[i];
                                        if (i > 0) airline = lines[i-1]; 
                                        break;
                                    }}
                                }}
                                
                                if (airline === "Unknown" && lines.length > 2) airline = lines[0];
                                
                                results.push({{ airline: airline, flight_number: flightNum, total_fare: cleanPrice }});
                            }});
                            return results;
                        """

                        all_flights_dict = {}
                        
                        for scroll_attempt in range(25):
                            current_flights = driver.execute_script(js_extract)
                            for f in current_flights:
                                uniq_key = f"{f['flight_number']}_{f['total_fare']}"
                                all_flights_dict[uniq_key] = f
                                
                            driver.execute_script("window.scrollBy(0, 900);")
                            time.sleep(1.2)
                            
                            at_bottom = driver.execute_script("return Math.ceil(window.innerHeight + window.scrollY) >= document.body.scrollHeight;")
                            if at_bottom:
                                time.sleep(1.5)
                                current_flights = driver.execute_script(js_extract)
                                for f in current_flights:
                                    uniq_key = f"{f['flight_number']}_{f['total_fare']}"
                                    all_flights_dict[uniq_key] = f
                                break

                        flights = list(all_flights_dict.values())
                        
                        if flights:
                            db_records = []
                            for idx, f in enumerate(flights):
                                base_fare = round(f['total_fare'] * 0.85, 2)
                                taxes = round(f['total_fare'] * 0.15, 2)
                                db_records.append((
                                    f['airline'], route, window, base_fare, taxes, 
                                    f['total_fare'], "MakeMyTrip", f"T{idx+1}", f['flight_number']
                                ))
                                
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
                                ''', db_records)
                                conn.commit()
                                
                            print(f"✅ Saved {len(flights)} verified flights (Attempt {attempt}).")
                            success = True
                            break
                        else:
                            raise Exception("Zero valid flights extracted.")
                            
                    except Exception as e:
                        print(f"⚠️ Attempt {attempt} failed: {e}")
                        session_warmed_up = False 
                        if "Network Problem" in str(e) or "WAF Block" in str(e):
                            print("🛡️ WAF Firewall Block detected! Quitting driver early and cooling down...")
                            break
                        if attempt == 1:
                            time.sleep(5)
                
                if success:
                    jitter = random.uniform(5.0, 9.0)
                    print(f"⏳ Cooling down for {round(jitter, 1)}s...")
                    time.sleep(jitter)

            if scraped_any_window:
                route_jitter = random.uniform(12.0, 18.0)
                print(f"\n⏳ Route complete. Cooling down for {round(route_jitter, 1)}s before next route...")
                time.sleep(route_jitter)

        except Exception as e:
            print(f"❌ Route Scrape failed. Exception: {e}")
            traceback.print_exc()
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            
            # Anti-bot safety break: Between every single route, rest for 15-25 seconds to keep IP clean
            if route_idx < len(top_20_routes) - 1:
                safety_sleep = random.uniform(15.0, 25.0)
                print(f"🛡️ Anti-Bot Safety Rest: Pausing for {round(safety_sleep, 1)}s before launching next route session...")
                time.sleep(safety_sleep)

    print("\n🎉 MakeMyTrip Batch Scraping Complete!")

if __name__ == "__main__":
    run_mmt_multi_scraper()
    os._exit(0)