from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import sqlite3
import re
import time

def run_akasa_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    airport_map = {
        "DEL": "Delhi", "BOM": "Mumbai", "BLR": "Bengaluru", 
        "HYD": "Hyderabad", "CCU": "Kolkata", "GOI": "Goa", 
        "MAA": "Chennai", "AMD": "Ahmedabad"
    }
    
    print(f"Launching Akasa Air Multi-Route Scraper for {len(top_20_routes)} routes...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                future_date_obj = datetime.now() + timedelta(days=window)
                future_date_str = future_date_obj.strftime("%d/%m/%Y")

                print(f"\n--- Akasa Scraping: {route} | T+{window} Days ({future_date_str}) ---")
                
                try:
                    page.goto("https://www.akasaair.com/", timeout=60000)
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(2000)
                    
                    # Origin Selection (Order-independent regex)
                    page.get_by_label("From *").click(force=True)
                    page.keyboard.type(origin, delay=150)
                    page.wait_for_timeout(1500)
                    origin_regex = re.compile(f"(?=.*{origin})(?=.*{airport_map[origin]})", re.IGNORECASE)
                    page.get_by_text(origin_regex).first.click(force=True)
                    page.wait_for_timeout(1000)
                    
                    # Destination Selection (Order-independent regex)
                    page.get_by_label("To *").click(force=True)
                    page.keyboard.type(dest, delay=150)
                    page.wait_for_timeout(1500)
                    dest_regex = re.compile(f"(?=.*{dest})(?=.*{airport_map[dest]})", re.IGNORECASE)
                    page.get_by_text(dest_regex).first.click(force=True)
                    page.wait_for_timeout(1000)
                    
                    # Date Selection
                    page.get_by_placeholder("Departure date").click(force=True)
                    page.wait_for_timeout(1000)
                    
                    target_day = str(int(future_date_obj.strftime("%d")))
                    page.get_by_text(target_day, exact=True).last.click(force=True)
                    page.wait_for_timeout(1000)
                    
                    page.get_by_text("Search Flights").first.click(force=True)
                    
                    print("Waiting 12 seconds for Akasa SPA to route to flight results...")
                    page.wait_for_timeout(12000)
                    
                    page.evaluate("window.scrollBy(0, 1000)")
                    page.wait_for_timeout(3000)
                    
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
                                    
                                    cursor.execute('''
                                        INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                    ''', ("Akasa Air", route, window, base_fare, taxes_fees, total_fare, "Akasa Direct"))
                                    
                                    inserted_count += 1
                    
                    conn.commit()
                    conn.close()
                    print(f"✅ Saved {inserted_count} records")
                                    
                except Exception as e:
                    print(f"Extraction error for {route} T+{window}:", e)
                
                time.sleep(5)

        browser.close()
        print("\nAkasa Air Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_akasa_scraper()