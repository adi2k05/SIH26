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
    
    print("Launching Akasa Air Scraper (React Event Dispatch Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                future_date_obj = datetime.now() + timedelta(days=window)
                print(f"\n--- Akasa Scraping: {route} | T+{window} Days ---")
                
                context = browser.new_context(viewport={"width": 1920, "height": 1080})
                page = context.new_page() 
                
                try:
                    page.goto("https://www.akasaair.com/", timeout=60000)
                    page.wait_for_timeout(4000) 
                    
                    # 1. Origin Input
                    loc_from = page.locator("#From")
                    loc_from.click(force=True)
                    page.wait_for_timeout(1000)
                    loc_from.fill("")
                    page.wait_for_timeout(500)
                    page.keyboard.type(origin, delay=300) 
                    page.wait_for_timeout(3500) 
                    
                    page.evaluate(f'''(iata) => {{
                        let els = Array.from(document.querySelectorAll('*')).filter(e => e.textContent.trim() === iata && e.children.length === 0);
                        for(let e of els) {{ if(e.closest('div, ul, li')) {{ e.click(); return; }} }}
                    }}''', origin)
                    
                    page.wait_for_timeout(3000) 
                    
                    # 2. Destination Input
                    loc_to = page.locator("#To")
                    loc_to.click(force=True) 
                    page.wait_for_timeout(1000)
                    loc_to.fill("")
                    page.wait_for_timeout(500)
                    page.keyboard.type(dest, delay=300) 
                    page.wait_for_timeout(3500) 
                    
                    page.evaluate(f'''(iata) => {{
                        let els = Array.from(document.querySelectorAll('*')).filter(e => e.textContent.trim() === iata && e.children.length === 0);
                        for(let e of els) {{ if(e.closest('div, ul, li')) {{ e.click(); return; }} }}
                    }}''', dest)
                            
                    page.wait_for_timeout(2000)
                    
                    # 3. Open Date Picker
                    page.get_by_placeholder(re.compile(r"Departure date", re.I)).click(force=True)
                    page.wait_for_timeout(2000) # Increased to allow calendar animations to finish
                    
                    # 4. Advance calendar if target month isn't visible
                    target_month_year = future_date_obj.strftime("%B %Y")
                    # Removes leading zero for single-digit days so it strictly matches UI text
                    target_day = str(int(future_date_obj.strftime("%d"))) 
                    
                    for _ in range(5):
                        if page.get_by_text(target_month_year, exact=True).is_visible():
                            break
                        page.evaluate('''() => {
                            let btns = Array.from(document.querySelectorAll('button, svg'));
                            let nextBtn = btns.find(b => b.className && typeof b.className === 'string' && b.className.toLowerCase().includes('next') || (b.getAttribute('aria-label') || '').toLowerCase().includes('next'));
                            if (nextBtn) { let parent = nextBtn.closest('button'); if(parent) parent.click(); else nextBtn.click(); }
                        }''')
                        page.wait_for_timeout(800)
                    
                    # 5. React-Bubbling Date Dispatch (Fixes weekend selection failures)
                    js_click_logic = f"""
                    () => {{
                        let targetDay = '{target_day}';
                        let targetMonthYear = '{target_month_year}';
                        let monthHeaders = Array.from(document.querySelectorAll('*')).filter(el => el.textContent.trim() === targetMonthYear);
                        
                        for (let header of monthHeaders) {{
                            let container = header.parentElement;
                            for (let i = 0; i < 6; i++) {{
                                if (container) {{
                                    // Strategy A: Find leaf nodes (handles nested weekend spans)
                                    let leafNodes = Array.from(container.querySelectorAll('*')).filter(el => 
                                        el.textContent.trim() === targetDay && el.children.length === 0
                                    );
                                    if (leafNodes.length > 0) {{
                                        let target = leafNodes[0];
                                        target.click();
                                        target.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
                                        return true;
                                    }}
                                    
                                    // Strategy B: Fallback for standard cells with embedded prices
                                    let cells = container.querySelectorAll('div, button, td');
                                    for (let cell of cells) {{
                                        if (cell.innerText) {{
                                            let lines = cell.innerText.trim().split('\\n');
                                            if (lines.length > 0 && lines[0].trim() === targetDay) {{
                                                cell.click();
                                                cell.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
                                                return true;
                                            }}
                                        }}
                                    }}
                                }}
                                if (container) container = container.parentElement;
                            }}
                        }}
                        return false;
                    }}
                    """
                    page.evaluate(js_click_logic)
                    page.wait_for_timeout(1500)
                    
                    # 6. Search Flights
                    page.get_by_text("Search Flights").first.click(force=True)
                    
                    flights_loaded = False
                    for _ in range(35):
                        try:
                            body_text = page.locator("body").inner_text()
                            if body_text.count("₹") > 4 or body_text.count("Rs") > 4:
                                flights_loaded = True
                                break
                        except Exception:
                            pass
                        page.wait_for_timeout(1000)
                        
                    if not flights_loaded:
                        print("⚠️ Timeout: Flights did not render.")
                        continue
                    
                    # 7. Extract Data
                    page_text = page.locator("body").inner_text()
                    lines = [line.strip() for line in page_text.split('\n') if line.strip()]
                    
                    fares = [int(re.sub(r'[^\d]', '', line)) for line in lines if ('₹' in line or 'Rs' in line) and re.sub(r'[^\d]', '', line)]
                    valid_fares = [f for f in fares if 1500 < f < 75000]
                    
                    # 8. Insert Records
                    if valid_fares:
                        with sqlite3.connect('airfare_index.db') as conn:
                            conn.executemany('''
                                INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', [("Akasa Air", route, window, round(f * 0.85, 2), round(f * 0.15, 2), f, "Akasa Direct") for f in valid_fares])
                            conn.commit()
                        print(f"✅ Saved {len(valid_fares)} direct records.")
                    else:
                        print("⚠️ No valid fares found on page.")
                                    
                except Exception as e:
                    print(f"❌ Extraction error: {e}")
                
                finally:
                    context.close()
                
                time.sleep(2)

        browser.close()
        print("\nAkasa Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_akasa_scraper()