from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import sqlite3
import re

def run_indigo_test():
    origin = "DEL"
    dest = "BOM"
    advance_window = 7
    future_date_obj = datetime.now() + timedelta(days=advance_window)
    
    print(f"Launching IndiGo Firefox Scraper for {origin}-{dest} (T+{advance_window} Days)...")

    with sync_playwright() as p:
        # 1. Switch to Firefox to bypass Chromium XHR blocking
        browser = p.firefox.launch(headless=False)
        
        # 2. ignore_https_errors bypasses the "Secure Connection Failed" Akamai trap
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True 
        )
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
            
            # Target the specific date number on the calendar
            target_day = str(int(future_date_obj.strftime("%d")))
            page.locator(".ui-datepicker-calendar").get_by_text(target_day, exact=True).last.click(force=True)
            page.wait_for_timeout(1000)
            
            # Click Search
            page.get_by_text("Search Flight").first.click(force=True)
            
            print("Waiting dynamically for IndiGo flights to render...")
            for attempt in range(15):
                current_text = page.locator("body").inner_text()
                if "₹" in current_text or "Rs" in current_text:
                    print(f"-> Flights loaded in ~{attempt + 1} seconds!")
                    break
                page.wait_for_timeout(1000)
            
            page.evaluate("window.scrollBy(0, 1000)")
            page.wait_for_timeout(2000)
            
            page_text = page.locator("body").inner_text()
            lines = [line.strip() for line in page_text.split('\n') if line.strip()]
            
            conn = sqlite3.connect('airfare_index.db')
            cursor = conn.cursor()
            inserted_count = 0
            
            for i, line in enumerate(lines):
                if "₹" in line or "Rs" in line:
                    clean_text = line.replace("₹", "").replace("Rs", "").replace(",", "").strip()
                    
                    if re.match(r'^\d{4,5}$', clean_text):
                        total_fare = int(clean_text)
                        
                        if 1500 < total_fare < 75000:
                            base_fare = round(total_fare * 0.85, 2)
                            taxes_fees = round(total_fare * 0.15, 2)
                            route = f"{origin}-{dest}"
                            
                            cursor.execute('''
                                INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', ("IndiGo", route, advance_window, base_fare, taxes_fees, total_fare, "IndiGo Direct"))
                            
                            inserted_count += 1
                            break # Grab top result to prevent dupes
            
            conn.commit()
            conn.close()
            print(f"✅ IndiGo: Saved {inserted_count} direct records.")
                            
        except Exception as e:
            print("Extraction error:", e)

        browser.close()

if __name__ == "__main__":
    run_indigo_test()