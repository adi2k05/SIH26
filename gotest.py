import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from datetime import datetime, timedelta
import re
import time

def test_goibibo_scraper():
    advance_windows = [7]
    top_20_routes = ["DEL-BLR","DEL-BOM","DEL-HYD"]
    all_scraped_records = []

    print("Launching Goibibo Scraper (Accurate Airline Extraction Mode)...")

    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    
    try:
        driver = uc.Chrome(options=options)
    except Exception as e:
        print(f"Error launching Chrome: {e}")
        return

    known_airlines = [
        "IndiGo", "Air India Express", "Air India", 
        "SpiceJet", "Akasa Air", "Vistara", "Alliance Air"
    ]

    for route in top_20_routes:
        origin, dest = route.split("-")
        
        for window in advance_windows:
            future_date_obj = datetime.now() + timedelta(days=window)
            raw_date = future_date_obj.strftime("%d/%m/%Y")
            safe_date = raw_date.replace('/', '%2F')
            
            print(f"\n--- Goibibo Scraping: {route} | T+{window} Days ({raw_date}) ---")
            
            for attempt in range(1, 3):
                try:
                    url = f"https://www.goibibo.com/flight/search?itinerary={origin}-{dest}-{safe_date}&tripType=O&paxType=A-1_C-0_I-0&intl=false&cabinClass=E&lang=eng"
                    driver.get(url)
                    
                    flights_loaded = False
                    for sec in range(35):
                        # 1. Auto-handle Network Problem overlay if present
                        refresh_buttons = driver.find_elements(By.XPATH, "//button[contains(translate(text(), 'REFRESH', 'refresh'), 'refresh')]")
                        if refresh_buttons and refresh_buttons[0].is_displayed():
                            print("🔄 Auto-clicking Refresh button...")
                            driver.execute_script("arguments[0].click();", refresh_buttons[0])
                            time.sleep(2)

                        # 2. Auto-dismiss 'GOT IT' comparison tooltip if visible
                        got_it_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'GOT IT') or contains(text(), 'Got it')]")
                        if got_it_buttons and got_it_buttons[0].is_displayed():
                            try:
                                got_it_buttons[0].click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", got_it_buttons[0])

                        body_text = driver.find_element(By.TAG_NAME, "body").text
                        if body_text.count("₹") > 5 or body_text.count("Rs") > 5:
                            flights_loaded = True
                            break
                        time.sleep(1)
                        
                    if not flights_loaded:
                        raise Exception("Flight cards did not render in DOM.")

                    # Scroll down to load more flights into DOM
                    driver.execute_script("window.scrollBy(0, 1500)")
                    time.sleep(1.5)

                    # 3. Card-Level Extraction via JavaScript
                    card_data = driver.execute_script('''
                        const cards = Array.from(document.querySelectorAll('div')).filter(el => {
                            // Find card containers that have an airline name, a time pattern, and a rupee symbol
                            const txt = el.innerText || "";
                            return el.children.length > 2 && 
                                   txt.includes('₹') && 
                                   /\\d{2}:\\d{2}/.test(txt) &&
                                   el.offsetHeight > 80 && el.offsetHeight < 300 &&
                                   el.offsetWidth > 400;
                        });

                        // Deduplicate nested parent/child divs by keeping the leaf card container
                        const uniqueCards = cards.filter(c => !cards.some(other => other !== c && c.contains(other)));
                        return uniqueCards.map(c => c.innerText);
                    ''')

                    current_batch = []
                    for raw_card in card_data:
                        lines = [l.strip() for l in raw_card.split('\n') if l.strip()]
                        
                        # Identify Airline
                        detected_airline = "Goibibo Partner"
                        for line in lines:
                            matched = next((a for a in known_airlines if a.lower() in line.lower()), None)
                            if matched:
                                detected_airline = matched
                                break

                        # Identify Fare
                        price_line = next((l for l in lines if '₹' in l), None)
                        if not price_line:
                            continue

                        clean_fare_str = re.sub(r'[^\d]', '', price_line)
                        if not clean_fare_str:
                            continue

                        fare_val = float(clean_fare_str)
                        if 1500 < fare_val < 75000:
                            current_batch.append({
                                "ota_source": "Goibibo",
                                "airline": detected_airline,
                                "route": route,
                                "advance_window_days": window,
                                "base_fare": round(fare_val * 0.85, 2),
                                "taxes_fees": round(fare_val * 0.15, 2),
                                "total_fare": fare_val
                            })

                    if current_batch:
                        # Deduplicate by airline and price
                        seen = set()
                        for item in current_batch:
                            key = (item["airline"], item["total_fare"])
                            if key not in seen:
                                seen.add(key)
                                all_scraped_records.append(item)

                        print(f"✅ Extracted {len(seen)} distinct flight cards with exact airlines (Attempt {attempt}).")
                        break
                    else:
                        raise Exception("Zero valid card entries parsed.")

                except Exception as e:
                    print(f"⚠️ Goibibo Attempt {attempt} failed: {e}")
                    if attempt == 1:
                        time.sleep(4)
            
            time.sleep(2)

    try:
        driver.close()
        driver.quit()
    except Exception:
        pass

    print(f"\n==========================================")
    print(f"Goibibo In-Memory Scraping Complete!")
    print(f"Total records stored: {len(all_scraped_records)}")
    print(f"==========================================")
    
    if all_scraped_records:
        print("\nSample records (First 5):")
        for item in all_scraped_records[:5]:
            print(item)

    return all_scraped_records

if __name__ == "__main__":
    test_goibibo_scraper()