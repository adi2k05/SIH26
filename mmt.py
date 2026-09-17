import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from datetime import datetime, timedelta
import time
import traceback
import sys
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

def dismiss_login_modal(driver):
    print("Waiting for initial dynamic promo modal...")
    wait = WebDriverWait(driver, 8)
    try:
        close_btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'span[data-cy="closeModal"], .commonModal__close')))
        time.sleep(0.5)
        try:
            close_btn.click()
        except:
            driver.execute_script("arguments[0].click();", close_btn)
        print("✅ Modal closed.")
        time.sleep(1)
    except:
        pass

    driver.execute_script("""
        let m = document.querySelector('div[data-cy="outsideModal"], .imageSliderModal, .loginModal');
        if (m) { m.remove(); }
    """)

def run_mmt_uc_scraper():
    route = "DEL-BOM"
    origin, dest = route.split("-")
    window_days = 1

    target_date = datetime.now() + timedelta(days=window_days)
    aria_date_str = target_date.strftime("%a %b %d %Y")
    display_date = target_date.strftime("%d/%m/%Y")
    extracted_data_list = []

    print(f"Launching MMT Scraper: {route} | {display_date}...")

    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    
    driver = uc.Chrome(options=options)
    wait = WebDriverWait(driver, 15)

    try:
        driver.get("https://www.makemytrip.com/")
        dismiss_login_modal(driver)

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
            driver.execute_script(js_click_date)
        time.sleep(1.5)

        # 4. Search
        print("Submitting search...")
        search_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.widgetSearchBtn, p[data-cy="submit"] a')))
        ActionChains(driver).move_to_element(search_btn).click().perform()

        # 5. Wait for Results Page (Updated with specific React classes from DevTools)
        print("Waiting for search results to load...")
        wait_long = WebDriverWait(driver, 45)
        wait_long.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".listingCard, .listingCardWrap, .flightCard_airlineHeading")))
        time.sleep(3)

        # Handle Infinite Scrolling
        print("Scrolling to load lazy-rendered flights...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        for scroll_attempt in range(12):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                # Slight bump up and down to trigger stuck lazy-loaders
                driver.execute_script("window.scrollBy(0, -500);")
                time.sleep(0.5)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                if driver.execute_script("return document.body.scrollHeight") == last_height:
                    break
            last_height = new_height

        # 6. Extract with STRICT Filtering and Exact Selectors
        print("Extracting and filtering data...")
        js_extract = f"""
            let results = [];
            // Target the main wrapper for each flight
            let cards = document.querySelectorAll('.listingCard, .listingCardWrap, div[class*="listingCard"]');
            
            cards.forEach(card => {{
                // STRICT FILTER: Parse origin and destination from the card
                let airports = Array.from(card.querySelectorAll('.flightCard_airport')).map(el => el.innerText.trim().substring(0,3));
                if (airports.length >= 2) {{
                    let cardOrigin = airports[0];
                    let cardDest = airports[airports.length - 1];
                    // Skip 'nearby airport' flights (e.g. HDO, NMI)
                    if (cardOrigin !== '{origin}' || cardDest !== '{dest}') {{
                        return; 
                    }}
                }}

                // Use the exact classes found in the DevTools inspection
                let airline = card.querySelector('.flightCard_airlineHeading')?.innerText.trim() || "Unknown";
                let flightNum = card.querySelector('.flightCard_airlineSub')?.innerText.trim() || "";
                
                let priceEl = card.querySelector('.blackText.fontSize18');
                if (priceEl) {{
                    let cleanPrice = parseInt(priceEl.innerText.replace(/[^0-9]/g, ''));
                    if (!isNaN(cleanPrice) && cleanPrice > 1000) {{
                        results.push({{ 
                            airline: airline, 
                            flight_number: flightNum, 
                            total_fare: cleanPrice 
                        }});
                    }}
                }}
            }});
            return results;
        """
        
        flights = driver.execute_script(js_extract)

        print(f"✅ Extracted {len(flights)} strictly matching flight records!")
        for f in flights:
            f['route'] = route
            f['advance_window_days'] = window_days
            f['travel_date'] = display_date
            f['ota_source'] = "MakeMyTrip"
            extracted_data_list.append(f)
            
        for idx, item in enumerate(extracted_data_list[:15]):
            print(f"[{idx+1}] {item}")
            
        if len(extracted_data_list) > 15:
            print(f"... and {len(extracted_data_list) - 15} more.")

    except Exception as e:
        print(f"❌ Scrape failed. Exception: {e}")
        traceback.print_exc()
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    run_mmt_uc_scraper()