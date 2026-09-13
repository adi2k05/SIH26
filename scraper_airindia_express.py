from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import time


def run_airindia_express_scraper():
    origin = "DEL"
    dest = "BOM"
    origin_city = "New Delhi"
    dest_city = "Mumbai"
    advance_windows = [7, 1, 15, 45]

    arr = []

    print("Launching Air India Express Chrome Scraper (List Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        for window in advance_windows:
            future_date_obj = datetime.now() + timedelta(days=window)
            target_day = future_date_obj.day
            target_month_year = future_date_obj.strftime("%B %Y")

            print(f"\n--- Air India Express Scraping: {origin}-{dest} | T+{window} Days ({future_date_obj.strftime('%d/%m/%Y')}) ---")

            for attempt in range(1, 3):
                page = context.new_page()
                try:
                    page.goto("https://www.airindiaexpress.com/", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(4000)

                    try:
                        page.get_by_text("Accept All", exact=True).first.click(force=True, timeout=3000)
                    except Exception:
                        pass
                    page.wait_for_timeout(500)

                    page.get_by_text("Flying from", exact=True).first.click(force=True, timeout=5000)
                    page.wait_for_timeout(800)
                    page.get_by_text(origin_city, exact=True).first.click(force=True, timeout=5000)
                    page.wait_for_timeout(1000)
                    page.get_by_text(dest_city, exact=True).first.click(force=True, timeout=5000)
                    page.wait_for_timeout(1000)

                    page.get_by_text("Departure", exact=True).first.click(force=True, timeout=5000)
                    page.wait_for_timeout(1200)

                    result = page.evaluate('''([targetDay, targetMonthYear]) => {
                        const headers = Array.from(document.querySelectorAll('*')).filter(e =>
                            e.children.length === 0 && e.textContent.trim() === targetMonthYear && e.offsetParent !== null
                        );
                        if (headers.length === 0) return null;
                        let container = headers[0];
                        for (let i = 0; i < 6; i++) {
                            container = container.parentElement;
                            if (!container) return null;
                            const dayCells = container.querySelectorAll('.new-day.day:not(.disabled)');
                            if (dayCells.length > 20) {
                                const match = Array.from(dayCells).find(c => {
                                    const dnum = c.querySelector('.new-calender-day');
                                    return dnum && dnum.textContent.trim() === String(targetDay);
                                });
                                if (!match) return null;
                                const priceEl = match.querySelector('.new-calender-day-price');
                                return priceEl ? priceEl.textContent.trim() : null;
                            }
                        }
                        return null;
                    }''', [target_day, target_month_year])

                    if not result:
                        raise Exception(f"No fare found in calendar for {target_month_year} day {target_day}.")

                    total_fare = float(result.replace("₹", "").replace(",", "").strip())

                    arr.append({
                        "airline": "Air India Express",
                        "route": f"{origin}-{dest}",
                        "advance_window_days": window,
                        "base_fare": round(total_fare * 0.85, 2),
                        "taxes_fees": round(total_fare * 0.15, 2),
                        "total_fare": total_fare,
                        "ota_source": "Air India Express Direct"
                    })
                    print(f"✅ Air India Express T+{window}: captured fare ₹{total_fare}.")
                    page.close()
                    break

                except Exception as e:
                    print(f"⚠️ Air India Express T+{window} Attempt {attempt} failed: {e}")
                    page.close()
                    if attempt == 1:
                        time.sleep(3)

            time.sleep(2)

        browser.close()

    print("\n==========================================")
    print("Air India Express In-Memory Scraping Complete!")
    print(f"Total records stored: {len(arr)}")
    print("==========================================")
    for item in arr:
        print(item)

    return arr


if __name__ == "__main__":
    run_airindia_express_scraper()
