from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import sqlite3
import re

def run_scraper():
    future_date = (datetime.now() + timedelta(days=7)).strftime("%d/%m/%Y")
    route = "DEL-BOM"
    advance_window = 7
    
    url = f"https://flight.easemytrip.com/FlightList/Index?srch=DEL-Delhi-India|BOM-Mumbai-India|{future_date}&px=1-0-0&cbn=0&ar=undefined&isSplit=false&isOneway=true&isFreeFlight=false"

    print(f"Target Date (T+7): {future_date}")
    print("Launching stealth browser...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("Navigating to EaseMyTrip...")
        page.goto(url, timeout=60000)
        
        print("Waiting for flight data to load (12 seconds)...")
        page.wait_for_timeout(12000) 

        print("\n--- EXTRACTING AND SAVING FARES ---")
        
        try:
            page_text = page.locator("body").inner_text()
            # Clean up empty lines so the data is packed tightly
            lines = [line.strip() for line in page_text.split('\n') if line.strip()]
            
            airlines = ["IndiGo", "Air India", "SpiceJet", "Akasa Air", "Air India Express"]
            
            conn = sqlite3.connect('airfare_index.db')
            cursor = conn.cursor()
            inserted_count = 0
            
            for i, line in enumerate(lines):
                if any(airline in line for airline in airlines):
                    matched_airline = next(airline for airline in airlines if airline in line)
                    
                    # Look ahead up to 15 lines for the price pattern
                    for j in range(1, 15):
                        if i + j < len(lines):
                            clean_text = lines[i+j].replace("₹", "").replace("Rs", "").strip()
                            
                            # Regex: Matches formats like "5,432" or "12400"
                            if re.match(r'^\d{1,2},\d{3}$', clean_text) or re.match(r'^\d{4,5}$', clean_text):
                                numeric_fare = int(clean_text.replace(',', ''))
                                
                                # Outlier filter: Real domestic flights are rarely under ₹1500
                                if numeric_fare > 1500:
                                    cursor.execute('''
                                        INSERT INTO raw_fares (airline, route, advance_window_days, extracted_fare)
                                        VALUES (?, ?, ?, ?)
                                    ''', (matched_airline, route, advance_window, numeric_fare))
                                    
                                    print(f"--> Saved to DB: {matched_airline} | {route} | ₹ {numeric_fare}")
                                    inserted_count += 1
                                    break 
            
            conn.commit()
            conn.close()
            
            if inserted_count == 0:
                print("⚠️ No fares inserted! A popup might be blocking the screen, or the layout changed.")
                            
        except Exception as e:
            print("Extraction error:", e)

        browser.close()
        print(f"\nPhase 2 Complete. {inserted_count} records saved to SQLite!")

if __name__ == "__main__":
    run_scraper()