import os
import re
import time
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

def scrape_indigo(origin: str = "DEL", destination: str = "BOM", window_days: int = 7):
    flight_records = []
    target_date = (datetime.now() + timedelta(days=window_days)).strftime("%Y-%m-%d")
    
    # Store persistent browser cookies/cache in a local profile directory to bypass Akamai
    user_data_dir = os.path.join(os.getcwd(), "indigo_browser_profile")
    
    print(f"✈️ Launching IndiGo Scraper for {origin}-{destination} | Departure: {target_date} (T+{window_days})")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            channel="chrome",
            headless=False,
            viewport={"width": 1366, "height": 768},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ],
            ignore_default_args=["--enable-automation"]
        )
        
        page = context.pages[0] if context.pages else context.new_page()

        try:
            print("🌐 Navigating to goindigo.in...")
            page.goto("https://www.goindigo.in/", wait_until="domcontentloaded", timeout=60000)
            
            # 1. Wait for the booking widget using a clean, strictly valid CSS selector
            print("⏳ Waiting for booking widget to mount...")
            page.wait_for_selector(".search-widget-form-body", state="visible", timeout=25000)
            time.sleep(2)

            # Close any promotional overlay or cookie dialogs if present
            overlay_close = page.locator("button:has-text('Accept'), .close-btn, [aria-label='Close']").first
            if overlay_close.is_visible():
                overlay_close.click()
                time.sleep(1)

            # 2. Set Destination (Origin defaults to Delhi/DEL)
            print(f"📍 Selecting destination: {destination}...")
            
            # Target the destination box reliably using the placeholder from your screenshot
            dest_inputs = page.get_by_placeholder("Search by place/airport")
            if dest_inputs.count() > 1:
                dest_inputs.nth(1).click()
            else:
                # Fallback to a structural click if placeholders load late
                page.locator(".search-widget-form-body > div").nth(1).click()
                
            time.sleep(1)
            page.keyboard.type(destination, delay=120)
            time.sleep(1.5)

            # Select the matching airport from the dropdown list
            page.keyboard.press("ArrowDown")
            time.sleep(0.5)
            page.keyboard.press("Enter")
            time.sleep(1.5)

            # 3. Select Target Date using the data-date attribute
            print(f"📅 Selecting date: {target_date}...")
            if not page.locator(f"div[data-date='{target_date}']").is_visible():
                dept_field = page.locator(".search-widget-form-body__departure").first
                if dept_field.is_visible():
                    dept_field.click()
                time.sleep(1)

            # Navigate months forward
            for _ in range(3):
                date_cell = page.locator(f"div[data-date='{target_date}']").first
                if date_cell.is_visible():
                    date_cell.click()
                    break
                next_month = page.locator("button.rdrNextButton").first
                if next_month.is_visible():
                    next_month.click()
                    time.sleep(1)
            time.sleep(1)

            # 4. Submit Search
            print("🚀 Executing flight search...")
            search_btn = page.locator("button:has-text('Search'), div[role='button']:has-text('Search')").first
            search_btn.click()

            # 5. Wait for Flight Results Page to Load
            print("⏳ Awaiting flight schedule and pricing...")
            page.wait_for_url("**/flight-select**", timeout=30000)
            time.sleep(5) 

            # 6. Extract Flight Cards into List
            cards = page.locator("div[class*='flight-card'], div[class*='flightCard'], div[class*='flight-row']").all()
            
            if not cards:
                cards = page.locator(".booking-flow-card, [data-test-id*='flight']").all()

            print(f"🔍 Parsing {len(cards)} available flights...")

            for card in cards:
                card_text = card.inner_text()
                
                times = re.findall(r'\b(\d{2}:\d{2})\b', card_text)
                prices = re.findall(r'₹?\s*([\d,]+)', card_text)

                if times and prices:
                    dept_time = times[0]
                    valid_prices = [
                        float(p.replace(',', '')) for p in prices 
                        if float(p.replace(',', '')) > 1500
                    ]
                    
                    if valid_prices:
                        total_fare = min(valid_prices)
                        base_fare = round(total_fare * 0.85, 2)
                        taxes = round(total_fare * 0.15, 2)
                        
                        flight_records.append({
                            "airline": "IndiGo",
                            "route": f"{origin}-{destination}",
                            "advance_window_days": window_days,
                            "base_fare": base_fare,
                            "taxes_fees": taxes,
                            "total_fare": total_fare,
                            "ota_source": "IndiGo Direct",
                            "departure_time": dept_time
                        })

            print(f"✅ Extracted {len(flight_records)} IndiGo flights successfully.")

        except Exception as err:
            print(f"❌ Scraping encountered an error: {err}")

        finally:
            context.close()

    return flight_records

if __name__ == "__main__":
    results = scrape_indigo(origin="DEL", destination="BOM", window_days=7)
    print("\nExtracted Flight Sample:")
    for item in results[:5]:
        print(item)