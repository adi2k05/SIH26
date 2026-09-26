from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta
import sqlite3
import re
import time
import os
import shutil  # Added for cache cleaning

def reset_profile_directory(profile_dir):
    """Nukes the user profile directory to eliminate tracking history upon block."""
    if os.path.exists(profile_dir):
        try:
            shutil.rmtree(profile_dir, ignore_errors=True)
            print("🗑️ Reset Goibibo profile directory for a clean fingerprint.")
        except Exception as e:
            print(f"⚠️ Failed to delete profile directory: {e}")

def launch_goibibo_browser(p, user_data_dir):
    """Helper function to cleanly launch/relaunch the browser context."""
    return p.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        channel="chrome",
        headless=False,
        viewport={"width": 1920, "height": 1080},
        args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        ignore_default_args=["--enable-automation"]
    )

def is_already_scraped(route, window, source):
    if os.environ.get("FORCE_RESCRAPE") == "1":
        return False
    if not os.path.exists('airfare_index.db'):
        return False
    with sqlite3.connect('airfare_index.db') as conn:
        c = conn.cursor()
        try:
            c.execute("""
                SELECT COUNT(*) FROM raw_fares 
                WHERE route = ? AND advance_window_days = ? AND ota_source = ? 
                AND date(timestamp) = date(datetime('now', '+5 hours', '+30 minutes'))
            """, (route, window, source))
            return c.fetchone()[0] > 0
        except sqlite3.OperationalError:
            return False

def run_goibibo_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    print("Launching Goibibo Aggregator Scraper (Pipeline Mode | Profile Purging Active)...")

    user_data_dir = os.path.join(os.getcwd(), "goibibo_browser_profile")
    routes_processed = 0

    with sync_playwright() as p:
        context = launch_goibibo_browser(p, user_data_dir)
        page = context.pages[0] if context.pages else context.new_page()

        # --- 1. WARM UP SESSION ---
        print("🌐 Initializing session on Goibibo homepage...")
        try:
            page.goto("https://www.goibibo.com/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            page.evaluate("""() => {
                let closeBtn = document.querySelector('span[class*="close"], button[class*="close"], [aria-label="Close"]');
                if (closeBtn) closeBtn.click();
            }""")
        except Exception:
            pass

        # --- 2. ITERATE ROUTES & WINDOWS ---
        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                if is_already_scraped(route, window, "Goibibo"):
                    print(f"⏩ Goibibo: {route} | T+{window} already collected today. Skipping.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d/%m/%Y") 
                
                url = f"https://www.goibibo.com/flight/search?itinerary={origin}-{dest}-{date_str}&tripType=O&paxType=A-1_C-0_I-0&intl=false&cabinClass=E&lang=eng"
                print(f"\n--- Goibibo Scraping: {route} | T+{window} Days ({date_str}) ---")
                
                success = False

                for attempt in range(1, 3):
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(4500)

                        page.evaluate("window.scrapedFlights = {};")

                        page.evaluate("""() => {
                            let closeBtn = document.querySelector('span[class*="close"], button[class*="close"], [aria-label="Close"], img[alt*="close"], div[class*="modal"] span');
                            if (closeBtn) closeBtn.click();
                            
                            let overlays = document.querySelectorAll('div[class*="modal"], div[class*="overlay"], div[role="dialog"]');
                            overlays.forEach(el => {
                                if (el.innerText.includes("Login") || el.innerText.includes("Signup") || el.innerText.includes("Mobile Number")) {
                                    el.remove();
                                }
                            });
                            document.body.style.overflow = 'auto';
                        }""")
                        
                        body_text = page.locator("body").inner_text().lower()
                        if "network problem" in body_text or "unable to connect" in body_text:
                            raise Exception("Network block detected on direct URL.")

                        print("📜 Scrolling and extracting virtualized flights...")
                        last_height = page.evaluate("document.body.scrollHeight")
                        
                        for step in range(25):
                            page.evaluate("""() => {
                                let btns = Array.from(document.querySelectorAll('button, span, div'));
                                let okayBtn = btns.find(b => b.innerText && (b.innerText.includes('OKAY, GOT IT!') || b.innerText.includes('GOT IT')));
                                if (okayBtn) okayBtn.click();
                                
                                let closeIcon = document.querySelector('[class*="crossIcon"], [class*="icon-close"], span.close');
                                if (closeIcon) closeIcon.click();
                            }""")
                            
                            page.evaluate("""() => {
                                let cards = document.querySelectorAll('div[data-test="component-clusterItem"], div.ListingCardWrap, div.sbox-flight-item');
                                if (cards.length === 0) cards = document.querySelectorAll('div[class*="cluster"]');
                                
                                cards.forEach(card => {
                                    let text = card.innerText || "";
                                    
                                    if (!text.toLowerCase().includes('non stop') && !text.toLowerCase().includes('non-stop')) {
                                        return; 
                                    }
                                    
                                    let airlineEl = card.querySelector('.airlineName');
                                    let airline = airlineEl ? airlineEl.innerText.trim() : "Unknown";
                                    
                                    let fliCodeEl = card.querySelector('.fliCode');
                                    let flightNo = fliCodeEl ? fliCodeEl.innerText.trim().replace(' ', '-') : "";
                                    
                                    if (!flightNo) {
                                        let flightMatch = text.match(/([A-Z0-9]{2})\\s*(\\d{3,4})/i);
                                        flightNo = flightMatch ? (flightMatch[1].toUpperCase() + "-" + flightMatch[2]) : "";
                                    }
                                    
                                    let times = text.match(/\\b(\\d{2}:\\d{2})\\b/g) || [];
                                    let depTime = times.length > 0 ? times[0] : "";
                                    
                                    let priceMatches = text.match(/[₹|Rs]\\s*([\\d,]+)/g) || [];
                                    let cleanPrices = priceMatches.map(p => parseInt(p.replace(/[^0-9]/g, ''))).filter(p => p > 1500 && p < 100000);
                                    
                                    if (flightNo && cleanPrices.length > 0) {
                                        let minFare = Math.min(...cleanPrices);
                                        let key = flightNo + "_" + minFare + "_" + depTime;
                                        
                                        window.scrapedFlights[key] = {
                                            airline: airline,
                                            flight_no: flightNo,
                                            departure_time: depTime,
                                            base_fare: Math.round(minFare * 0.85),
                                            taxes_fees: Math.round(minFare * 0.15),
                                            total_fare: minFare,
                                            ota_source: "Goibibo"
                                        };
                                    }
                                });
                            }""")
                            
                            page.evaluate("window.scrollBy(0, 800);")
                            page.wait_for_timeout(1000)
                            
                            new_height = page.evaluate("document.body.scrollHeight")
                            if new_height == last_height and step > 5:
                                break
                            last_height = new_height

                        flight_records = page.evaluate("Object.values(window.scrapedFlights);")

                        if flight_records:
                            with sqlite3.connect('airfare_index.db') as conn:
                                conn.executemany('''
                                    INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', [
                                    (
                                        rec['airline'], 
                                        route, 
                                        window, 
                                        rec['base_fare'], 
                                        rec['taxes_fees'], 
                                        rec['total_fare'], 
                                        rec['ota_source'], 
                                        rec['departure_time'], 
                                        rec['flight_no']
                                    ) for rec in flight_records
                                ])
                                conn.commit()
                            print(f"✅ Saved {len(flight_records)} strict Non-Stop records to DB for T+{window}.")
                        else:
                            body_text = page.locator("body").inner_text()
                            if "no flights" in body_text.lower() or "sold out" in body_text.lower() or "no results" in body_text.lower():
                                with sqlite3.connect('airfare_index.db') as conn:
                                    conn.execute('''
                                        INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                        VALUES (?, ?, ?, NULL, NULL, NULL, ?, NULL, NULL)
                                    ''', ("Goibibo Aggregator", route, window, "Goibibo"))
                                    conn.commit()
                                print(f"ℹ️ Goibibo returned no flights for T+{window}. Logging NULL.")
                            else:
                                raise Exception("No valid non-stop flights extracted despite page load.")

                        success = True
                        break # Exit attempt loop on success

                    except Exception as e:
                        print(f"⚠️ Goibibo Attempt {attempt} failed: {e}")
                        
                        # --- ENGAGE PROFILE PURGE DEFENSE ON SOFT BLOCK/HTTP ERROR ---
                        if attempt == 1:
                            print("🛡️ WAF/HTTP2 block detected! Engaging defense protocols (Clearing Profile)...")
                            try:
                                context.close()
                            except:
                                pass
                            time.sleep(3) 
                            reset_profile_directory(user_data_dir)
                            time.sleep(5)
                            print("🔄 Spinning up a fresh browser for retry...")
                            context = launch_goibibo_browser(p, user_data_dir)
                            page = context.pages[0] if context.pages else context.new_page()

                if success:
                    time.sleep(3)

            # --- BATCH RESTART EVERY 3 ROUTES TO SHED TRACKING ---
            routes_processed += 1
            if routes_processed > 0 and routes_processed % 3 == 0:
                print("\n🔄 Batch limit reached (3 routes). Purging profile to drop WAF tracking...")
                context.close()
                time.sleep(3)
                reset_profile_directory(user_data_dir)
                time.sleep(5)
                context = launch_goibibo_browser(p, user_data_dir)
                page = context.pages[0] if context.pages else context.new_page()

        context.close()
        print("\n🎉 Goibibo Pipeline Scraping Complete!")

if __name__ == "__main__":
    run_goibibo_scraper()