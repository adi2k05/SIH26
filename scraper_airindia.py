from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import json
import time


def run_airindia_scraper():
    origin = "DEL"
    dest = "BOM"
    advance_windows = [7, 1, 15, 45]

    arr = []

    print("Launching Air India Chrome Scraper (List Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        for window in advance_windows:
            future_date_obj = datetime.now() + timedelta(days=window)
            target_iso = future_date_obj.strftime("%Y-%m-%d")
            target_aria = f"{future_date_obj.month}/{future_date_obj.day}/{future_date_obj.year}"

            print(f"\n--- Air India Scraping: {origin}-{dest} | T+{window} Days ({target_iso}) ---")

            for attempt in range(1, 3):
                page = context.new_page()
                fare_payloads = []

                def handle_response(response, bucket=fare_payloads):
                    try:
                        if "airline-fares/v1/search" in response.url:
                            bucket.append(response.text())
                    except Exception:
                        pass

                page.on("response", handle_response)
                try:
                    page.goto("https://www.airindia.com/", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(4000)

                    try:
                        page.get_by_text("Accept All", exact=True).first.click(force=True, timeout=5000)
                    except Exception:
                        pass
                    page.wait_for_timeout(1000)

                    page.get_by_text("One Way", exact=True).first.click(force=True, timeout=5000)
                    page.wait_for_timeout(500)

                    origin_input = page.locator('input.ai-autocomplete-input').nth(0)
                    origin_input.click(force=True)
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    page.keyboard.type(origin, delay=150)
                    page.wait_for_timeout(1200)
                    page.locator("mat-option").first.click(force=True, timeout=5000)
                    page.wait_for_timeout(800)

                    dest_input = page.locator('input.ai-autocomplete-input').nth(1)
                    dest_input.click(force=True)
                    page.wait_for_timeout(300)
                    page.keyboard.type(dest, delay=150)
                    page.wait_for_timeout(1200)
                    page.locator("mat-option").first.click(force=True, timeout=5000)
                    page.wait_for_timeout(800)

                    page.get_by_text("Select Date", exact=True).first.click(force=True, timeout=5000)
                    page.wait_for_timeout(1200)

                    # Advance the calendar if the target month isn't in the two visible months yet
                    for _ in range(3):
                        if page.locator(f'button.mat-calendar-body-cell[aria-label="{target_aria}"]').count() > 0:
                            break
                        page.get_by_role("button", name="Next month").first.click(force=True)
                        page.wait_for_timeout(600)

                    page.locator(f'button.mat-calendar-body-cell[aria-label="{target_aria}"]').first.click(force=True, timeout=5000)
                    page.wait_for_timeout(1000)

                    page.get_by_role("button", name="Search", exact=True).first.click(force=True, timeout=8000)

                    print("Waiting for the airline-fares API response...")
                    for _ in range(15):
                        if fare_payloads:
                            break
                        page.wait_for_timeout(1000)

                    if not fare_payloads:
                        raise Exception("airline-fares/v1/search never responded.")

                    payload = json.loads(fare_payloads[-1])
                    if not payload.get("data") or not payload["data"].get("fares"):
                        raise Exception(f"Unexpected fare payload: {payload}")

                    match = next((f for f in payload["data"]["fares"] if f.get("departureDate") == target_iso), None)
                    if not match:
                        raise Exception(f"No fare entry for {target_iso} in payload.")

                    price = match["totalPrice"]
                    total_fare = float(price["total"])
                    base_fare = float(price["base"])
                    taxes_fees = float(price["tax"])

                    arr.append({
                        "airline": "Air India",
                        "route": f"{origin}-{dest}",
                        "advance_window_days": window,
                        "base_fare": base_fare,
                        "taxes_fees": taxes_fees,
                        "total_fare": total_fare,
                        "ota_source": "Air India Direct"
                    })
                    print(f"✅ Air India T+{window}: captured fare ₹{total_fare}.")
                    page.close()
                    break

                except Exception as e:
                    print(f"⚠️ Air India T+{window} Attempt {attempt} failed: {e}")
                    page.close()
                    if attempt == 1:
                        time.sleep(3)

            time.sleep(2)

        browser.close()

    print("\n==========================================")
    print("Air India In-Memory Scraping Complete!")
    print(f"Total records stored: {len(arr)}")
    print("==========================================")
    for item in arr:
        print(item)

    return arr


if __name__ == "__main__":
    run_airindia_scraper()
