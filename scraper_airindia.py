from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import re
import time

def run_airindia_scraper(discovery_mode=True):
    advance_windows = [7]  # Testing with T+7 to verify DOM logic first
    top_20_routes = ["DEL-BOM"]  # Testing single route

    all_scraped_records = []

    print("Launching Air India Direct Scraper (List Testing Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d/%m/%Y") 
                
                print(f"\n--- Air India Scraping: {route} | T+{window} Days ---")
                
                for attempt in range(1, 3):
                    page = context.new_page()
                    captured_endpoints = []

                    def handle_response(response, bucket=captured_endpoints):
                        try:
                            ctype = response.headers.get("content-type", "")
                            if "json" not in ctype:
                                return
                            url_lower = response.url.lower()
                            keywords = ["search", "avail", "fare", "flight", "price", "ibe", "booking"]
                            if not any(k in url_lower for k in keywords):
                                return
                            preview = ""
                            try:
                                preview = response.text()[:300]
                            except Exception:
                                pass
                            print(f"[NETWORK JSON] {response.status} {response.url}")
                            if preview:
                                print(f"    preview: {preview}")
                            bucket.append(response.url)
                        except Exception:
                            pass

                    page.on("response", handle_response)
                    try:
                        # 1. Navigate to the Homepage
                        page.goto("https://www.airindia.com/", wait_until="domcontentloaded", timeout=60000)
                        
                        # Cookie Popup Evasion
                        try:
                            print("Checking for cookie consent popup...")
                            accept_button = page.locator('button:has-text("Accept")').first
                            accept_button.wait_for(state="visible", timeout=4000)
                            accept_button.click()
                            print("✅ Cookie popup dismissed.")
                        except Exception:
                            print("⚠️ Standard cookie button not detected, destroying overlays via JavaScript...")
                            page.evaluate('''() => {
                                const modals = document.querySelectorAll('div[id^="onetrust"], div[class*="cookie"], div[class*="overlay"], div[class*="modal"]');
                                modals.forEach(el => el.remove());
                                document.body.style.overflow = "auto";
                            }''')
                        
                        page.wait_for_timeout(2000)

                        # 2. Force "One Way" Selection
                        print("Setting journey to One Way...")
                        page.locator('label:has-text("One Way")').first.click()
                        page.wait_for_timeout(1000)

                        # 3. Fill Origin
                        print(f"Entering Origin: {origin}")
                        page.locator('input#From, input[aria-label*="From"], div:has-text("FROM")').first.click()
                        page.wait_for_timeout(500)
                        page.keyboard.type(origin, delay=150)
                        page.wait_for_timeout(1500)
                        page.keyboard.press("Enter")

                        # 4. Fill Destination
                        print(f"Entering Destination: {dest}")
                        page.locator('input#To, input[aria-label*="To"], div:has-text("TO")').first.click()
                        page.wait_for_timeout(500)
                        page.keyboard.type(dest, delay=150)
                        page.wait_for_timeout(1500)
                        page.keyboard.press("Enter")

                        # 5. Enter Date and Search
                        print(f"Entering Date: {date_str}")
                        try:
                            page.locator('input#ddate, input[placeholder*="Depart"]').first.fill(date_str)
                        except Exception:
                            page.keyboard.type(date_str, delay=100)

                        page.keyboard.press("Enter")
                        page.wait_for_timeout(1000)

                        print("Clicking Search...")
                        page.locator('button:has-text("Search"), button[aria-label*="Search"]').first.click()
                        
                        # 6. Let the SPA finish its background API calls
                        print("Waiting for network activity to settle...")
                        try:
                            page.wait_for_load_state("networkidle", timeout=45000)
                        except Exception:
                            print("networkidle wait timed out, continuing anyway")
                        page.wait_for_timeout(3000)

                        if discovery_mode:
                            print(f"Current URL after search: {page.url}")
                            print(f"Captured {len(captured_endpoints)} candidate JSON endpoints this run: {captured_endpoints}")
                            page.screenshot(path=f"debug_{route}_{window}_{attempt}.png", full_page=True)
                            with open(f"debug_{route}_{window}_{attempt}.html", "w", encoding="utf-8") as f:
                                f.write(page.content())
                            raise Exception("Discovery mode on: check the printed URL/endpoints and debug_*.png/.html, then set discovery_mode=False once the real fare endpoint is confirmed")

                        # 7. Extract Card Texts
                        raw_flight_texts = page.evaluate('''() => {
                            const detailsLinks = Array.from(document.querySelectorAll('a, button, span')).filter(el => el.innerText.includes('Flight Details'));
                            return detailsLinks.map(link => {
                                let card = link.parentElement.parentElement.parentElement.parentElement;
                                return card ? card.innerText : "";
                            });
                        }''')

                        current_batch = []
                        for raw_text in raw_flight_texts:
                            if not raw_text:
                                continue
                            
                            lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
                            price_line = next((line for line in lines if 'INR' in line), None)
                            if not price_line:
                                continue
                            
                            clean_price_str = re.sub(r'[^\d]', '', price_line.replace('INR', ''))
                            if not clean_price_str:
                                continue
                                
                            total_fare = float(clean_price_str)
                            if not (1500 < total_fare < 75000):
                                continue

                            airline_name = "Air India"
                            for line in lines[:3]:
                                if "Air India Express" in line:
                                    airline_name = "Air India Express"
                                    break

                            current_batch.append({
                                "ota_source": "Air India Direct",
                                "airline": airline_name,
                                "route": route,
                                "advance_window_days": window,
                                "base_fare": 0.0,
                                "taxes_fees": 0.0,
                                "total_fare": total_fare
                            })

                        if current_batch:
                            all_scraped_records.extend(current_batch)
                            print(f"✅ Extracted {len(current_batch)} direct flights (Attempt {attempt}).")
                            page.close()
                            break
                        else:
                            raise Exception("Zero valid fares parsed.")

                    except Exception as e:
                        print(f"⚠️ Air India Attempt {attempt} failed: {e}")
                        page.close()
                        if attempt == 1:
                            time.sleep(3)
                
                time.sleep(2)

        browser.close()
        
        print(f"\n==========================================")
        print(f"Air India In-Memory Scraping Complete!")
        print(f"Total records stored: {len(all_scraped_records)}")
        print(f"==========================================")
        
        if all_scraped_records:
            for item in all_scraped_records[:5]:
                print(item)
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import re
import time


def build_cleartrip_url(origin, dest, date_str):
    return (
        f"https://www.cleartrip.com/flights/results?"
        f"adults=1&childs=0&infants=0&class=Economy&depart_date={date_str}"
        f"&from={origin}&to={dest}&intl=false"
    )


def run_cleartrip_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL",
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL",
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI",
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM",
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]

    all_scraped_records = []

    print("Launching Cleartrip Multi-Route Scraper (List Mode, No DB)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        for route in top_20_routes:
            origin, dest = route.split("-")

            for window in advance_windows:
                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d/%m/%Y")
                print(f"\n--- Cleartrip Scraping: {route} | T+{window} Days ({date_str}) ---")

                for attempt in range(1, 3):
                    page = context.new_page()
                    try:
                        url = build_cleartrip_url(origin, dest, date_str)
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)

                        flights_loaded = False
                        for _ in range(25):
                            body_text = page.locator("body").inner_text()
                            if body_text.count("₹") > 5 or body_text.count("Rs") > 5:
                                flights_loaded = True
                                break
                            page.wait_for_timeout(1000)

                        if not flights_loaded:
                            raise Exception("Flight cards did not render in DOM.")

                        page.evaluate("window.scrollBy(0, 1500)")
                        page.wait_for_timeout(1500)

                        lines = [l.strip() for l in page.locator("body").inner_text().split('\n') if l.strip()]
                        fares = [int(re.sub(r'[^\d]', '', l)) for l in lines if ('₹' in l or 'Rs' in l) and re.sub(r'[^\d]', '', l)]
                        valid_fares = [f for f in fares if 1500 < f < 75000]

                        if valid_fares:
                            for f in valid_fares:
                                all_scraped_records.append({
                                    "airline": "Cleartrip Partner",
                                    "route": route,
                                    "advance_window_days": window,
                                    "base_fare": round(f * 0.85, 2),
                                    "taxes_fees": round(f * 0.15, 2),
                                    "total_fare": f,
                                    "ota_source": "Cleartrip"
                                })
                            print(f"✅ Collected {len(valid_fares)} records (Attempt {attempt}).")
                            page.close()
                            break
                        else:
                            raise Exception("Zero valid fare numbers parsed.")

                    except Exception as e:
                        print(f"⚠️ Cleartrip Attempt {attempt} failed: {e}")
                        page.close()
                        if attempt == 1:
                            time.sleep(5)

                time.sleep(2)

        browser.close()
        print(f"\n==========================================")
        print(f"Cleartrip Scraping Complete!")
        print(f"Total records stored: {len(all_scraped_records)}")
        print(f"==========================================")

        if all_scraped_records:
            for item in all_scraped_records[:5]:
                print(item)

    return all_scraped_records



if __name__ == "__main__":
    run_airindia_scraper(discovery_mode=True)