from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import re
import time


def run_indigo_scraper():
    origin = "DEL"
    dest = "BOM"
    advance_windows = [7, 1, 15, 45]

    arr = []

    print("Launching IndiGo Chrome Scraper (List Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        for window in advance_windows:
            future_date_obj = datetime.now() + timedelta(days=window)
            target_day = str(int(future_date_obj.strftime("%d")))
            target_month_year = future_date_obj.strftime("%B %Y")

            print(f"\n--- IndiGo Scraping: {origin}-{dest} | T+{window} Days ({future_date_obj.strftime('%d/%m/%Y')}) ---")

            for attempt in range(1, 3):
                page = context.new_page()
                try:
                    page.goto("https://www.goindigo.in/", timeout=60000)
                    page.wait_for_timeout(3000)

                    # Type Origin slowly
                    page.locator('input[placeholder="From"]').click(force=True)
                    page.keyboard.type(origin, delay=200)
                    page.wait_for_timeout(1000)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(1000)

                    # Type Destination slowly
                    page.locator('input[placeholder="To"]').click(force=True)
                    page.keyboard.type(dest, delay=200)
                    page.wait_for_timeout(1000)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(1000)

                    # Advance the calendar (T+45 can land a month or two ahead)
                    for _ in range(3):
                        month_header = page.locator(".ui-datepicker-group, .ui-datepicker-header").filter(has_text=target_month_year)
                        if month_header.count() > 0:
                            break
                        page.locator(".ui-datepicker-next").first.click(force=True)
                        page.wait_for_timeout(800)

                    # Target the specific date number on the calendar
                    page.locator(".ui-datepicker-calendar").get_by_text(target_day, exact=True).last.click(force=True)
                    page.wait_for_timeout(1000)

                    # Click Search
                    page.get_by_text("Search Flight").first.click(force=True)

                    print("Waiting dynamically for IndiGo flights to render...")
                    flights_loaded = False
                    for attempt_wait in range(20):
                        current_text = page.locator("body").inner_text()
                        if "₹" in current_text or "Rs" in current_text:
                            print(f"-> Flights loaded in ~{attempt_wait + 1} seconds!")
                            flights_loaded = True
                            break
                        page.wait_for_timeout(1000)

                    if not flights_loaded:
                        raise Exception("Flight cards did not render in DOM.")

                    page.evaluate("window.scrollBy(0, 1000)")
                    page.wait_for_timeout(2000)

                    lines = [line.strip() for line in page.locator("body").inner_text().split('\n') if line.strip()]

                    found_fare = None
                    for line in lines:
                        if "₹" in line or "Rs" in line:
                            clean_text = line.replace("₹", "").replace("Rs", "").replace(",", "").strip()
                            if re.match(r'^\d{4,5}$', clean_text):
                                candidate = int(clean_text)
                                if 1500 < candidate < 75000:
                                    found_fare = candidate
                                    break  # Grab top result to prevent dupes

                    if found_fare is not None:
                        arr.append({
                            "airline": "IndiGo",
                            "route": f"{origin}-{dest}",
                            "advance_window_days": window,
                            "base_fare": round(found_fare * 0.85, 2),
                            "taxes_fees": round(found_fare * 0.15, 2),
                            "total_fare": found_fare,
                            "ota_source": "IndiGo Direct"
                        })
                        print(f"✅ IndiGo T+{window}: captured fare ₹{found_fare}.")
                        page.close()
                        break
                    else:
                        raise Exception("Zero valid fares parsed.")

                except Exception as e:
                    print(f"⚠️ IndiGo T+{window} Attempt {attempt} failed: {e}")
                    page.close()
                    if attempt == 1:
                        time.sleep(3)

            time.sleep(2)

        browser.close()

    print("\n==========================================")
    print("IndiGo In-Memory Scraping Complete!")
    print(f"Total records stored: {len(arr)}")
    print("==========================================")
    for item in arr:
        print(item)

    return arr


if __name__ == "__main__":
    run_indigo_scraper()
