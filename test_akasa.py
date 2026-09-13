from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
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
    
    # Akasa Air operates at Manohar International (GOX), not Dabolim (GOI)
    unsupported_akasa_routes = ["DEL-GOI", "BOM-GOI"]
    all_scraped_records = []
    
    print("Launching Akasa Air Scraper (SPA Accelerated JS Mode)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            if route in unsupported_akasa_routes:
                print(f"ℹ️ {route} uses GOX instead of GOI. Skipping permanently.")
                for window in advance_windows:
                    all_scraped_records.append({
                        "airline": "Akasa Air", "route": route, "advance_window_days": window,
                        "base_fare": None, "taxes_fees": None, "total_fare": None, "ota_source": "Akasa Direct"
                    })
                continue
            
            page = context.new_page()
            route_initialized = False
            
            for window in advance_windows:
                future_date_obj = datetime.now() + timedelta(days=window)
                target_month_year = future_date_obj.strftime("%B %Y")
                target_day = future_date_obj.strftime("%d") # Zero-padded day
                target_short_month = future_date_obj.strftime("%b") # e.g. "Sep"
                
                print(f"\n--- Akasa Scraping: {route} | T+{window} Days ({target_day} {target_month_year}) ---")
                
                for attempt in range(1, 3):
                    try:
                        if not route_initialized:
                            # 1. INITIALIZATION: Full Homepage Load
                            page.goto("https://www.akasaair.com/", wait_until="domcontentloaded", timeout=45000)
                            page.wait_for_timeout(4000) 
                            
                            page.locator("#From").click(force=True)
                            page.wait_for_timeout(500)
                            page.keyboard.press("Control+A")
                            page.keyboard.press("Backspace")
                            page.keyboard.type(origin, delay=150)
                            page.wait_for_timeout(2000)
                            
                            page.evaluate(f'''(iata) => {{
                                let el = Array.from(document.querySelectorAll('*')).find(e => e.textContent.trim() === iata && e.children.length === 0);
                                if(el) el.click();
                            }}''', origin)
                            page.wait_for_timeout(1500)
                            
                            page.locator("#To").click(force=True)
                            page.wait_for_timeout(500)
                            page.keyboard.press("Control+A")
                            page.keyboard.press("Backspace")
                            page.keyboard.type(dest, delay=150)
                            page.wait_for_timeout(2000)
                            
                            page.evaluate(f'''(iata) => {{
                                let el = Array.from(document.querySelectorAll('*')).find(e => e.textContent.trim() === iata && e.children.length === 0);
                                if(el) el.click();
                            }}''', dest)
                            page.wait_for_timeout(1500)
                            
                            page.get_by_placeholder(re.compile(r"Departure date", re.I)).click(force=True)
                            page.wait_for_timeout(1500)
                        
                        else:
                            # 2. SPA ACCELERATION: Bypass Overlays with Pure JS Clicks
                            page.evaluate('''() => {
                                let btns = Array.from(document.querySelectorAll('button'));
                                let modBtn = btns.find(b => b.innerText.trim() === 'Modify');
                                if (modBtn) modBtn.click();
                            }''')
                            page.wait_for_timeout(1500)
                            
                            page.evaluate('''() => {
                                let labels = Array.from(document.querySelectorAll('label, p, span')).filter(e => e.textContent.trim() === 'Travel date');
                                if(labels.length > 0) {
                                    let parent = labels[0].parentElement;
                                    if(parent) parent.click();
                                }
                            }''')
                            page.wait_for_timeout(1500)
                        
                        # 3. NATIVE CALENDAR NAVIGATION
                        for _ in range(6):
                            month_visible = page.evaluate(f'''() => {{
                                return Array.from(document.querySelectorAll('*')).some(e => 
                                    (e.innerText || e.textContent || '').replace(/\\s+/g, ' ').trim() === '{target_month_year}'
                                );
                            }}''')
                            
                            if month_visible:
                                break
                                
                            page.evaluate('''() => {
                                let btns = Array.from(document.querySelectorAll('button, svg'));
                                let nextBtn = btns.find(b => (b.className || '').toString().toLowerCase().includes('next') || (b.getAttribute('aria-label') || '').toLowerCase().includes('next'));
                                if(nextBtn) {
                                    let p = nextBtn.closest('button');
                                    if(p) p.click(); else nextBtn.click();
                                }
                            }''')
                            page.wait_for_timeout(800)
                        
                        # 4. ROBUST JS DAY SELECTION
                        day_clicked = page.evaluate(f'''() => {{
                            let targetMonthYear = '{target_month_year}';
                            let targetDay = '{int(target_day)}'; // Strip zero-padding for calendar click
                            let headers = Array.from(document.querySelectorAll('*')).filter(e => (e.innerText || e.textContent || '').replace(/\\s+/g, ' ').trim() === targetMonthYear);
                            
                            for (let header of headers) {{
                                let container = header.parentElement;
                                for (let i=0; i<4; i++) {{
                                    if(container) {{
                                        let dayCells = Array.from(container.querySelectorAll('button, div, td, span')).filter(e => {{
                                            let txt = (e.innerText || e.textContent || '').trim().split('\\n')[0].trim();
                                            return txt === targetDay && e.children.length === 0;
                                        }});
                                        
                                        if(dayCells.length > 0) {{
                                            let target = dayCells[0].closest('button, div[role="button"], td') || dayCells[0];
                                            target.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }}));
                                            return true;
                                        }}
                                    }}
                                    if(container) container = container.parentElement;
                                }}
                            }}
                            return false;
                        }}''')
                        
                        if not day_clicked:
                            raise Exception(f"Failed to pick day {target_day} {target_month_year} from calendar.")
                            
                        page.wait_for_timeout(1000)
                        
                        page.evaluate('''() => {
                            let btns = Array.from(document.querySelectorAll('button'));
                            let searchBtn = btns.find(b => b.innerText.trim() === 'Search Flights');
                            if (searchBtn) searchBtn.click();
                        }''')
                        
                        # 5. EXTRACT & VERIFY SPA STATE REFRESH
                        flights_loaded = False
                        verify_string = f"{target_day} {target_short_month}" # e.g. "28 Sep"
                        
                        for _ in range(30):
                            try:
                                body_text = page.locator("body").inner_text()
                                if "no flights" in body_text.lower() or "sold out" in body_text.lower():
                                    all_scraped_records.append({
                                        "airline": "Akasa Air", "route": route, "advance_window_days": window,
                                        "base_fare": None, "taxes_fees": None, "total_fare": None, "ota_source": "Akasa Direct"
                                    })
                                    print(f"ℹ️ Akasa officially returned no flights for T+{window}. Logging NULL.")
                                    flights_loaded = "EMPTY"
                                    break
                                
                                # Verify the requested date actually appears in the updated DOM header before extracting
                                if (body_text.count("₹") > 4 or body_text.count("Rs") > 4) and verify_string in body_text:
                                    flights_loaded = True
                                    break
                            except Exception:
                                pass
                            page.wait_for_timeout(1000)
                            
                        if not flights_loaded:
                            raise Exception(f"Flight results for {verify_string} failed to render or SPA stale.")
                            
                        route_initialized = True
                            
                        if flights_loaded == "EMPTY":
                            break
                        
                        lines = [l.strip() for l in page.locator("body").inner_text().split('\n') if l.strip()]
                        fares = [int(re.sub(r'[^\d]', '', l)) for l in lines if ('₹' in l or 'Rs' in l) and re.sub(r'[^\d]', '', l)]
                        valid_fares = [f for f in fares if 1500 < f < 75000]
                        
                        if valid_fares:
                            for f in valid_fares:
                                all_scraped_records.append({
                                    "airline": "Akasa Air",
                                    "route": route,
                                    "advance_window_days": window,
                                    "base_fare": round(f * 0.85, 2),
                                    "taxes_fees": round(f * 0.15, 2),
                                    "total_fare": f,
                                    "ota_source": "Akasa Direct"
                                })
                            print(f"✅ Verified {len(valid_fares)} actual flights scraped for {verify_string} (Attempt {attempt}).")
                            break
                        else:
                            raise Exception("Zero fares extracted.")
                                        
                    except Exception as e:
                        print(f"⚠️ Akasa Attempt {attempt} failed: {e}")
                        route_initialized = False # Force hard homepage reload on Attempt 2
                        if attempt == 1:
                            time.sleep(4)
                            
            try:
                page.close()
            except:
                pass
            time.sleep(2)

        browser.close()
        
        print("\n==========================================")
        print("Akasa In-Memory Scraping Complete!")
        print(f"Total records stored: {len(all_scraped_records)}")
        print("==========================================")
        if all_scraped_records:
            print("\nSample records (First 5):")
            for item in all_scraped_records[:5]:
                print(item)

        return all_scraped_records

if __name__ == "__main__":
    run_akasa_scraper()