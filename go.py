import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from datetime import datetime, timedelta
import sqlite3
import json
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

def run_goibibo_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]

    print("Launching Goibibo API Sniffer (React Autosuggest Mode)...")

    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    
    try:
        driver = uc.Chrome(options=options)
        uc.Chrome.__del__ = lambda self: None 
    except Exception as e:
        print(f"Error launching Chrome: {e}")
        return

    for route in top_20_routes:
        origin, dest = route.split("-")
        
        for window in advance_windows:
            if is_already_scraped(route, window, "Goibibo"):
                print(f"⏩ Goibibo: {route} | T+{window} already collected today. Skipping.")
                continue

            future_date_obj = datetime.now() + timedelta(days=window)
            target_month_year = future_date_obj.strftime("%B %Y")
            target_date_label = future_date_obj.strftime("%b %d %Y")

            print(f"\n--- Goibibo API Sniffing: {route} | T+{window} Days ({target_date_label}) ---")

            for attempt in range(1, 3):
                try:
                    driver.get("https://www.goibibo.com/")
                    wait = WebDriverWait(driver, 10)
                    time.sleep(4)
                    
                    # 1. Force kill the Login/Signup popup & click away
                    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(1)
                    ActionChains(driver).move_by_offset(5, 5).click().perform()
                    time.sleep(1)

                    # 2. Click the 'From' dummy box to trigger the React popup
                    from_dummy = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='From'] | //p[text()='Enter city or airport']")))
                    from_dummy.click()
                    time.sleep(1.5)

                    # 3. Locate the REAL (non-readonly) input injected by React and type Origin
                    real_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='text' and not(@readonly)]")))
                    real_input.send_keys(origin)
                    time.sleep(1.5)
                    
                    # Wait for Goibibo's revamped autocomplete dropdown, then click the first item
                    dropdown_items = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//ul[@id='autoSuggest-list']//li | //li[contains(@class, 'react-autosuggest__suggestion')] | //div[contains(@class, 'revampedSearchSuggestionItem')]")))
                    dropdown_items[0].click()
                    time.sleep(1)

                    # 4. The 'To' popup usually opens automatically. Find the active real input and type Destination.
                    real_input = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='text' and not(@readonly)]")))
                    real_input.send_keys(dest)
                    time.sleep(1.5)
                    
                    dropdown_items = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//ul[@id='autoSuggest-list']//li | //li[contains(@class, 'react-autosuggest__suggestion')] | //div[contains(@class, 'revampedSearchSuggestionItem')]")))
                    dropdown_items[0].click()
                    time.sleep(1)

                    # 5. Native Calendar Selection
                    for _ in range(8):
                        month_headers = driver.find_elements(By.XPATH, f"//div[contains(text(), '{target_month_year}')]")
                        if month_headers and month_headers[0].is_displayed():
                            break
                        
                        next_btn = driver.find_elements(By.XPATH, "//span[@aria-label='Next Month'] | //div[contains(@class, 'DayPicker-NavButton--next')]")
                        if next_btn:
                            next_btn[0].click()
                        time.sleep(0.5)

                    date_element = wait.until(EC.element_to_be_clickable((By.XPATH, f"//div[contains(@aria-label, '{target_date_label}')]")))
                    date_element.click()
                    time.sleep(1)

                    # 6. Flush logs & trigger Search
                    driver.get_log("performance")
                    search_btn = driver.find_elements(By.XPATH, "//span[text()='SEARCH'] | //a[contains(@class, 'widgetSearchBtn')] | //span[contains(@class, 'widgetSearchBtn')]")
                    if search_btn:
                        search_btn[0].click()

                    print("Waiting for Goibibo backend JSON API response via CDP...")
                    
                    # 7. CDP Log Polling Loop
                    valid_fares = []
                    for _ in range(25):
                        logs = driver.get_log("performance")
                        for log in logs:
                            try:
                                message = json.loads(log["message"])["message"]
                                if message["method"] == "Network.responseReceived":
                                    mime_type = message["params"]["response"]["mimeType"]
                                    
                                    if "application/json" in mime_type:
                                        request_id = message["params"]["requestId"]
                                        res = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                                        payload_str = res.get("body", "")
                                        
                                        if "onwardflights" in payload_str or "totalfare" in payload_str.lower():
                                            data = json.loads(payload_str)
                                            flights_list = data.get("data", {}).get("onwardflights", [])
                                            
                                            for f in flights_list:
                                                airline = f.get("airline") or f.get("carrier", {}).get("name") or "Goibibo Partner"
                                                fare_node = f.get("fare") or f.get("price") or {}
                                                total = fare_node.get("totalfare") or fare_node.get("totalPrice")
                                                
                                                if total and 1500 < float(total) < 75000:
                                                    base = fare_node.get("basefare") or (float(total) * 0.85)
                                                    tax = fare_node.get("taxes") or (float(total) * 0.15)
                                                    
                                                    valid_fares.append((
                                                        airline, route, window,
                                                        round(float(base), 2), round(float(tax), 2), float(total),
                                                        "Goibibo"
                                                    ))
                            except Exception:
                                continue
                                
                        if valid_fares:
                            break 
                            
                        time.sleep(1.5)

                    if not valid_fares:
                        raise Exception("Failed to intercept JSON API payload after clicking SEARCH.")

                    unique_batch = list(set(valid_fares))
                    
                    with sqlite3.connect('airfare_index.db') as conn:
                        conn.executemany('''
                            INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', unique_batch)
                        conn.commit()

                    print(f"✅ Intercepted {len(unique_batch)} distinct records directly from backend JSON (Attempt {attempt}).")
                    break

                except Exception as e:
                    print(f"⚠️ Goibibo Attempt {attempt} failed: {e}")
                    if "invalid session id" in str(e).lower() or "disconnected" in str(e).lower():
                        driver.quit()
                        driver = uc.Chrome(options=options)
                    if attempt == 1:
                        time.sleep(3)
                        
            time.sleep(2)

    try:
        driver.quit()
    except Exception:
        pass

    print("\nGoibibo Database Scraping Complete!")

if __name__ == "__main__":
    run_goibibo_scraper()