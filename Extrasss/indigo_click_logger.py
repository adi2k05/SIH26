import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from datetime import datetime, timedelta
import random
import time
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

def dismiss_overlays(driver):
    try:
        driver.execute_script("""
            let modals = document.querySelectorAll('div[data-cy="outsideModal"], .imageSliderModal, .loginModal, .overlay, .commonModal__close');
            modals.forEach(m => m.remove());
            document.body.style.overflow = 'auto';
        """)
    except:
        pass

def perform_ui_warmup(driver, wait, origin, dest, target_date):
    print("Performing UI Warmup (Bypassing Network Block)...")
    driver.get("https://www.makemytrip.com/")
    time.sleep(3)
    
    modal_start = time.time()
    while time.time() - modal_start < 5.0:
        try:
            close_btn = driver.find_element(By.CSS_SELECTOR, 'span[data-cy="closeModal"], .commonModal__close')
            if close_btn.is_displayed():
                driver.execute_script("arguments[0].click();", close_btn)
                break
        except:
            pass
        time.sleep(0.5)
        
    dismiss_overlays(driver)
    time.sleep(1)

    from_label = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'label[for="fromCity"]')))
    ActionChains(driver).move_to_element(from_label).click().perform()
    time.sleep(1)
    from_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input.react-autosuggest__input')))
    from_input.send_keys(origin)
    time.sleep(2) 
    driver.execute_script("let opt = document.querySelector('li[role=\"option\"]'); if(opt) opt.click();")
    time.sleep(1)

    try:
        to_input = driver.find_element(By.CSS_SELECTOR, 'input.react-autosuggest__input')
    except:
        to_label = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'label[for="toCity"]')))
        ActionChains(driver).move_to_element(to_label).click().perform()
        time.sleep(1)
        to_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input.react-autosuggest__input')))
    
    to_input.send_keys(dest)
    time.sleep(2)
    driver.execute_script("let opt = document.querySelector('li[role=\"option\"]'); if(opt) opt.click();")
    time.sleep(1)

    search_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.widgetSearchBtn, a.widgetSearchBtn, p[data-cy="submit"] button, p[data-cy="submit"] a')))
    ActionChains(driver).move_to_element(search_btn).click().perform()
    time.sleep(4)

def extract_flights_from_dom(driver, origin, dest):
    """Executes the JS block to extract currently visible flights"""
    js_extract = f"""
        let results = [];
        let cards = document.querySelectorAll('.listingCard, .listingCardWrap, div[class*="listingCard"]');
        
        cards.forEach(card => {{
            let cardText = card.innerText || "";
            let lowerText = cardText.toLowerCase();
            let lines = cardText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
            
            let hasOrigin = lines.some(l => new RegExp("\\\\b{origin}\\\\b").test(l));
            let hasDest = lines.some(l => new RegExp("\\\\b{dest}\\\\b").test(l));
            if (!hasOrigin || !hasDest) return;
            
            if ('{dest}' === 'BOM' && lowerText.includes('navi mumbai') && !lowerText.includes('mumbai')) return;
            if ('{origin}' === 'DEL' && (lowerText.includes('ghaziabad') || lowerText.includes('hindon')) && !lowerText.includes('new delhi')) return;
            
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
                    flightNum = lines[i].replace(/\\s+/, '-'); 
                    if (i > 0) airline = lines[i-1]; 
                    break;
                }}
            }}
            
            if (!flightNum) return;
            if (airline === "Unknown" && lines.length > 2) airline = lines[0];
            
            let depTimeNode = card.querySelector('.flightCard_time');
            let depTime = "Unknown";
            if (depTimeNode && /\\d{{2}}:\\d{{2}}/.test(depTimeNode.innerText)) {{
                depTime = depTimeNode.innerText.match(/\\b(\\d{{2}}:\\d{{2}})\\b/)[0];
            }} else {{
                let times = cardText.match(/\\b(\\d{{2}}:\\d{{2}})\\b/g) || [];
                if (times.length > 0) depTime = times[0];
            }}
            
            results.push({{ 
                airline: airline, 
                flight_number: flightNum, 
                departure_time: depTime, 
                total_fare: cleanPrice 
            }});
        }});
        return results;
    """
    
    extracted_dict = {}
    for scroll_attempt in range(20):
        current_flights = driver.execute_script(js_extract)
        for f in current_flights:
            uniq_key = f"{f['flight_number']}_{f['departure_time']}_{f['total_fare']}"
            extracted_dict[uniq_key] = f
            
        driver.execute_script("window.scrollBy(0, 900);")
        time.sleep(1.2)
        
        at_bottom = driver.execute_script("return Math.ceil(window.innerHeight + window.scrollY) >= document.body.scrollHeight;")
        if at_bottom:
            time.sleep(1.5)
            current_flights = driver.execute_script(js_extract)
            for f in current_flights:
                uniq_key = f"{f['flight_number']}_{f['departure_time']}_{f['total_fare']}"
                extracted_dict[uniq_key] = f
            break
            
    return list(extracted_dict.values())

def apply_stop_filter(driver, target_stop):
    """
    Clears all active stop filters, then specifically clicks the target filter (e.g. 'Non Stop' or '1 Stop')
    """
    driver.execute_script(f"""
        // 1. Clear any active 'applied' chips at the top of the screen
        let activeChips = Array.from(document.querySelectorAll('.appliedFilter .close, .appliedFilter svg, div[class*="appliedFilter"]'));
        activeChips.forEach(btn => btn.click());
        
        // 2. Identify the left sidebar pills
        let pills = Array.from(document.querySelectorAll('.filterPill'));
        
        // 3. Uncheck all stop filters to reset the board
        pills.forEach(p => {{
            if ((p.innerText.includes('Non Stop') || p.innerText.includes('1 Stop')) && p.className.includes('Active')) {{
                p.click();
            }}
        }});
    """)
    time.sleep(2) # Wait for DOM to reset
    
    driver.execute_script(f"""
        let pills = Array.from(document.querySelectorAll('.filterPill'));
        let targetPill = pills.find(p => p.innerText.includes('{target_stop}'));
        if (targetPill && !targetPill.className.includes('Active')) {{
            targetPill.click();
        }}
    """)
    time.sleep(4) # Wait for network request to fetch new filtered flights

def run_test():
    # TEST CONFIGURATION
    test_routes = [
        ("DEL", "BOM", 1), 
        ("BLR", "BOM", 7)
    ]

    print("Launching MakeMyTrip Filter Test...")
    user_data_dir = os.path.join(os.getcwd(), "mmt_browser_profile")
    
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument(f"--user-data-dir={user_data_dir}")
    
    driver = uc.Chrome(options=options, use_subprocess=True)
    wait = WebDriverWait(driver, 35)
    
    session_warmed_up = False

    try:
        for origin, dest, window in test_routes:
            target_date = datetime.now() + timedelta(days=window)
            url_date = target_date.strftime("%d/%m/%Y")
            
            print(f"\n==================================================")
            print(f"🛫 TESTING: {origin}-{dest} | T+{window} Days ({url_date})")
            print(f"==================================================")
            
            if not session_warmed_up:
                perform_ui_warmup(driver, wait, origin, dest, target_date)
                session_warmed_up = True
            else:
                direct_url = f"https://www.makemytrip.com/flight/search?itinerary={origin}-{dest}-{url_date}&tripType=O&paxType=A-1_C-0_I-0&intl=false&cabinClass=E&lang=eng"
                driver.get(direct_url)
                time.sleep(4)
                
            dismiss_overlays(driver)
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".listingCard, .listingCardWrap, div[class*='listingCard']")))
            
            all_collected_flights = []
            
            # --- PHASE 1: NON-STOP FLIGHTS ---
            print("\n🔄 Phase 1: Applying 'Non Stop' filter...")
            apply_stop_filter(driver, 'Non Stop')
            print("📜 Scrolling and extracting Non-Stop flights...")
            non_stop_flights = extract_flights_from_dom(driver, origin, dest)
            print(f"✅ Extracted {len(non_stop_flights)} Non-Stop flights.")
            all_collected_flights.extend(non_stop_flights)
            
            # Scroll back to top before applying next filter
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            # --- PHASE 2: 1-STOP FLIGHTS ---
            print("\n🔄 Phase 2: Applying '1 Stop' filter...")
            apply_stop_filter(driver, '1 Stop')
            print("📜 Scrolling and extracting 1-Stop flights...")
            one_stop_flights = extract_flights_from_dom(driver, origin, dest)
            print(f"✅ Extracted {len(one_stop_flights)} 1-Stop flights.")
            all_collected_flights.extend(one_stop_flights)
            
            # --- RESULTS SUMMARY ---
            print(f"\n📊 TOTAL COMBINED EXTRACTION FOR {origin}-{dest}: {len(all_collected_flights)} flights")
            print("Sample Data:")
            for idx, flight in enumerate(all_collected_flights[:5]):
                print(f"  {idx+1}. {flight['airline']} {flight['flight_number']} | Dep: {flight['departure_time']} | Fare: ₹{flight['total_fare']}")
            if len(all_collected_flights) > 5:
                print("  ...")
            
            time.sleep(3)

    except Exception as e:
        print(f"❌ Test failed: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_test()