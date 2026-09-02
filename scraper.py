from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta

def run_scraper():
    # SIH Requirement: Calculate T+7 days for the Advance-Purchase Window
    future_date = (datetime.now() + timedelta(days=7)).strftime("%d/%m/%Y")
    
    # Direct search URL trick (Bypasses the home page and manual clicking)
    url = f"https://flight.easemytrip.com/FlightList/Index?srch=DEL-Delhi-India|BOM-Mumbai-India|{future_date}&px=1-0-0&cbn=0&ar=undefined&isSplit=false&isOneway=true&isFreeFlight=false"

    print(f"Target Date (T+7): {future_date}")
    print("Launching stealth browser...")

    with sync_playwright() as p:
        # Launch browser. Headless=False means we can watch it work.
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("Navigating directly to flight search results...")
        page.goto(url, timeout=60000)
        
        # We must wait for the loading screen (the airplane animation) to disappear
        print("Waiting for flight data to load (12 seconds)...")
        page.wait_for_timeout(12000) 

        # Take a screenshot to prove we got the flight cards
        page.screenshot(path="flights_loaded.png")
        print("Screenshot saved as flights_loaded.png")

        print("\n--- EXTRACTING RAW FARES ---")
        
        try:
            # We extract all visible text from the page
            page_text = page.locator("body").inner_text()
            lines = page_text.split('\n')
            
            # The specific airlines MoSPI wants us to track
            airlines = ["IndiGo", "Air India", "SpiceJet", "Akasa Air", "Air India Express"]
            
            # Simple parsing: Find the airline name, then look slightly ahead for the ₹ price
            for i, line in enumerate(lines):
                if any(airline in line for airline in airlines):
                    print(f"Found Carrier: {line.strip()}")
                    # Look ahead up to 10 lines to find the associated fare
                    for j in range(1, 10):
                        if i + j < len(lines) and "₹" in lines[i+j]:
                            print(f"--> Fare Extracted: {lines[i+j].strip()}")
                            break
                            
        except Exception as e:
            print("Extraction error:", e)

        browser.close()
        print("\nPhase 1 Complete. Scraping Engine is functional!")

if __name__ == "__main__":
    run_scraper()