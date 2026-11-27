from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import sqlite3
import random
import shutil
import time
import os

class YatraBlockException(Exception):
    """Raised when Yatra returns a 404 soft-block or Akamai challenge."""
    pass

def reset_profile_directory(profile_dir):
    """Clears browser profile cookies/storage to shed Akamai _abck session tracking."""
    if os.path.exists(profile_dir):
        try:
            shutil.rmtree(profile_dir, ignore_errors=True)
            print("🗑️ Reset Yatra browser profile to clear Akamai tracking cookies.")
        except Exception as e:
            print(f"⚠️ Could not delete profile directory: {e}")

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
                AND total_fare IS NOT NULL
                AND date(timestamp) = date(datetime('now', '+5 hours', '+30 minutes'))
            """, (route, window, source))
            return c.fetchone()[0] > 0
        except sqlite3.OperationalError:
            return False

def launch_yatra_session(p, user_data_dir):
    """Launches real Chrome with stealth and warms up www.yatra.com for a valid _abck cookie."""
    context = p.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        channel="chrome",
        headless=(os.environ.get("HEADLESS_MODE") == "1"),
        viewport={"width": 1920, "height": 1080},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--test-type"
        ],
        ignore_default_args=["--enable-automation"]
    )
    page = context.pages[0] if context.pages else context.new_page()

    print("Initializing Yatra gateway session & generating Akamai sensor cookie...")
    try:
        page.goto("https://www.yatra.com", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3500)
        # Simulate brief human telemetry so Akamai's sensor script validates the session
        page.mouse.move(random.randint(300, 900), random.randint(200, 600))
        page.evaluate("window.scrollBy(0, 300);")
        page.wait_for_timeout(1500)
    except Exception as e:
        print(f"⚠️ Gateway warmup warning: {e}")

    return context, page

def run_yatra_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    print("Launching Yatra Multi-Route Scraper (Original Trigger URL + Akamai Session Defense)...")
    user_data_dir = os.path.join(os.getcwd(), "yatra_browser_profile")
    routes_processed = 0

    with Stealth().use_sync(sync_playwright()) as p:
        context, page = launch_yatra_session(p, user_data_dir)

        try:
            for route in top_20_routes:
                origin, dest = route.split("-")
                scraped_any_window = False
                
                for window in advance_windows:
                    if is_already_scraped(route, window, "Yatra"):
                        print(f"⏩ Yatra: {route} | T+{window} already collected today. Skipping.")
                        continue

                    scraped_any_window = True
                    future_date_obj = datetime.now() + timedelta(days=window)
                    date_str = future_date_obj.strftime("%d/%m/%Y")
                    print(f"\n--- Yatra Scraping: {route} | T+{window} Days ({date_str}) ---")
                    
                    for attempt in range(1, 3):
                        try:
                            # Exact original working URL format
                            url = f"https://flight.yatra.com/air-search-ui/dom2/trigger?type=O&viewName=normal&flexi=0&noOfSegments=1&origin={origin}&originCountry=IN&destination={dest}&destinationCountry=IN&flight_depart_date={date_str}&ADT=1&CHD=0&INF=0&class=Economy&source=fresco-home"
                            
                            # Reuse the single warm tab instead of opening new tabs
                            page.goto(url, wait_until="domcontentloaded", timeout=50000)
                            
                            flights_loaded = False
                            for _ in range(40): 
                                try:
                                    body_text = page.locator("body").inner_text()
                                    lower_body = body_text.lower()

                                    if "404 not found" in lower_body or "uhmm.. can't find" in lower_body or "access denied" in lower_body:
                                        raise YatraBlockException("Yatra 404 / WAF soft-block triggered.")

                                    if "akamai" in lower_body or "waiting" in lower_body:
                                        page.wait_for_timeout(1000)
                                        continue

                                    if body_text.count("₹") > 4 or body_text.count("Rs") > 4:
                                        flights_loaded = True
                                        break
                                except YatraBlockException:
                                    raise
                                except Exception:
                                    page.wait_for_timeout(1000)
                                    continue
                                page.wait_for_timeout(1000)
                            
                            if not flights_loaded:
                                raise YatraBlockException("Flights not rendered (timeout or Akamai hold).")
                                
                            print("Page loaded. Executing adaptive scroll loop to trigger all lazy-rendered flight cards...")
                            expected_total = page.evaluate("""() => {
                                let m = document.body.innerText.match(/(\\d+)\\s+flights?/i);
                                return m ? parseInt(m[1]) : 0;
                            }""")
                            if expected_total > 0:
                                print(f"Target flight count from page header: {expected_total}")

                            prev_card_count = 0
                            no_new_streak = 0
                            for step in range(1, 80):
                                page.evaluate("window.scrollBy(0, 1000);")
                                page.wait_for_timeout(500)
                                
                                if step % 4 == 0:
                                    card_count = page.evaluate("document.querySelectorAll('article[data-flight-id], article.card-lift, .flightItem, div[class*=\"flightItem\"]').length")
                                    if expected_total > 0 and card_count >= expected_total:
                                        print(f"All {expected_total} flights fully rendered (step {step}).")
                                        break
                                        
                                    if card_count == prev_card_count:
                                        no_new_streak += 1
                                        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                                        page.wait_for_timeout(1000)
                                        if no_new_streak >= 3:
                                            print(f"Reached bottom of search results with {card_count} cards.")
                                            break
                                    else:
                                        no_new_streak = 0
                                        prev_card_count = card_count
                                        
                            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                            page.wait_for_timeout(2000)
                                
                            # --- ORIGINAL JAVASCRIPT DEEP EXTRACTION ---
                            valid_flights = page.evaluate(f"""() => {{
                                let records = [];
                                let cards = document.querySelectorAll('article[data-flight-id], article.card-lift, .flightItem, div[class*="flightItem"]');
                                
                                cards.forEach(card => {{
                                    if (card.classList && card.classList.contains('srp-offer-card')) {{
                                        return;
                                    }}
                                    let text = card.innerText || "";
                                    
                                    // 1. Strict Origin & Destination Check
                                    let cardOrig = "";
                                    let cardDest = "";
                                    
                                    let codes = Array.from(text.matchAll(/\\(([A-Z]{{3}})\\)/g)).map(m => m[1]);
                                    if (codes.length >= 2) {{
                                        cardOrig = codes[0];
                                        cardDest = codes[codes.length - 1];
                                    }}
                                    
                                    if (!cardOrig || !cardDest) {{
                                        let origNode = card.querySelector('.mob-origin');
                                        let destNode = card.querySelector('.arrival-details .mob-origin');
                                        if (origNode && destNode) {{
                                            let origMatch = origNode.innerText.match(/\\(([A-Z]{{3}})\\)/);
                                            let destMatch = destNode.innerText.match(/\\(([A-Z]{{3}})\\)/);
                                            if (origMatch) cardOrig = origMatch[1];
                                            if (destMatch) cardDest = destMatch[1];
                                        }}
                                    }}
                                    
                                    let flightId = card.getAttribute('data-flight-id') || "";
                                    if ((!cardOrig || !cardDest) && flightId.length >= 6 && /^[A-Z]{{6}}/.test(flightId)) {{
                                        cardOrig = flightId.slice(0, 3);
                                        let matchDest = flightId.match(/([A-Z]{{3}})[A-Z0-9]{{2}}\\d{{3,4}}[A-Z0-9]*_\\w+$/);
                                        cardDest = matchDest ? matchDest[1] : flightId.slice(3, 6);
                                    }}
                                    
                                    if (cardOrig !== '{origin}' || cardDest !== '{dest}') {{
                                        return;
                                    }}
                                    
                                    // 2. Extract Airline Name
                                    let airline = "";
                                    let logoImg = card.querySelector('img[alt*="logo" i]');
                                    if (logoImg && logoImg.getAttribute('alt')) {{
                                        airline = logoImg.getAttribute('alt').replace(/\\s*logo/i, '').trim();
                                    }}
                                    if (!airline) {{
                                        let airlineEl = card.querySelector('span[role="heading"]');
                                        if (airlineEl) {{
                                            airline = airlineEl.getAttribute('title') || airlineEl.innerText.trim();
                                        }}
                                    }}
                                    if (!airline) {{
                                        let pAir = card.querySelector('p[class*="font-semibold"]');
                                        if (pAir) {{
                                            airline = pAir.innerText.trim();
                                        }}
                                    }}
                                    if (!airline) {{
                                        airline = "Yatra Partner";
                                    }}
                                    
                                    // 3. Extract Flight Number
                                    let flightNo = "";
                                    if (flightId) {{
                                        let segMatches = Array.from(flightId.matchAll(/[A-Z]{{6}}([A-Z0-9]{{2}}\\d{{3,4}})/g)).map(m => m[1]);
                                        if (segMatches.length > 0) {{
                                            let flNums = segMatches.map(m => m.slice(0, 2) + '-' + m.slice(2));
                                            flightNo = Array.from(new Set(flNums)).join('/');
                                        }} else {{
                                            let mId = flightId.match(/^[A-Z]{{6}}([A-Z0-9]{{2}})(\\d{{3,4}})/);
                                            if (mId) flightNo = mId[1] + '-' + mId[2];
                                        }}
                                    }}
                                    if (!flightNo) {{
                                        let flNoEl = card.querySelector('.fl-no span, .font-lightgrey.fl-no');
                                        if (flNoEl && flNoEl.innerText.trim()) {{
                                            flightNo = flNoEl.innerText.trim();
                                        }}
                                    }}
                                    if (!flightNo) {{
                                        let pTags = card.querySelectorAll('p[class*="text-xs"], span');
                                        for (let p of pTags) {{
                                            let t = p.innerText ? p.innerText.trim() : "";
                                            if (/^[A-Z0-9]{{2}}[\\-\\s]?\\d{{3,4}}$/.test(t)) {{
                                                flightNo = t;
                                                break;
                                            }}
                                        }}
                                    }}
                                    if (!flightNo) {{
                                        let m = text.match(/\\b([A-Z0-9]{{2}})[\\-\\s]?(\\d{{3,4}})\\b/);
                                        flightNo = m ? (m[1] + '-' + m[2]) : "UNKNOWN";
                                    }} else {{
                                        flightNo = flightNo.replace(/\\s+/, '-');
                                        if (!flightNo.includes('-') && flightNo.length >= 3) {{
                                            flightNo = flightNo.slice(0, 2) + '-' + flightNo.slice(2);
                                        }}
                                    }}
                                    
                                    // 4. Extract Departure Time
                                    let timeEl = card.querySelector('.mob-time, p[class*="tabular-nums"][class*="font-bold"]');
                                    let depTime = timeEl ? timeEl.innerText.trim() : "";
                                    if (!depTime || !/^\\d{{2}}:\\d{{2}}$/.test(depTime)) {{
                                        let tMatch = text.match(/\\b(\\d{{2}}:\\d{{2}})\\b/);
                                        depTime = tMatch ? tMatch[0] : "00:00";
                                    }}
                                    
                                    // 5. Extract Price
                                    let cleanPrice = 0;
                                    let priceEl = card.querySelector('.ow-price-above-btn, .price, p[class*="font-extrabold"], p[class*="text-xl"]');
                                    if (priceEl && priceEl.innerText) {{
                                        let val = parseInt(priceEl.innerText.replace(/[^0-9]/g, ''));
                                        if (!isNaN(val) && val > 1000) cleanPrice = val;
                                    }}
                                    if (!cleanPrice) {{
                                        let pMatches = Array.from(text.matchAll(/[₹|Rs]\\s*([\\d,]+)/g))
                                                            .map(m => parseInt(m[1].replace(/,/g, '')))
                                                            .filter(v => !isNaN(v) && v > 1000);
                                        if (pMatches.length > 0) {{
                                            cleanPrice = Math.min(...pMatches);
                                        }}
                                    }}
                                    
                                    if (!isNaN(cleanPrice) && cleanPrice > 1000 && flightNo) {{
                                        records.push({{
                                            airline: airline,
                                            flight_no: flightNo,
                                            departure_time: depTime,
                                            fare: cleanPrice
                                        }});
                                    }}
                                }});
                                
                                // Deduplicate
                                let unique = {{}};
                                records.forEach(r => {{
                                    let key = r.flight_no + "_" + r.departure_time;
                                    if (!unique[key] || r.fare < unique[key].fare) {{
                                        unique[key] = r;
                                    }}
                                }});
                                return Object.values(unique);
                            }}""")
                            
                            if valid_flights:
                                with sqlite3.connect('airfare_index.db') as conn:
                                    conn.execute('''
                                        CREATE TABLE IF NOT EXISTS raw_fares (
                                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                                            timestamp DATETIME DEFAULT (datetime('now', '+5 hours', '+30 minutes')),
                                            airline TEXT, route TEXT, advance_window_days INTEGER, base_fare REAL, 
                                            taxes_fees REAL, total_fare REAL, ota_source TEXT, departure_time TEXT, flight_no TEXT
                                        )
                                    ''')
                                    conn.executemany('''
                                        INSERT INTO raw_fares (airline, route, advance_window_days, base_fare, taxes_fees, total_fare, ota_source, departure_time, flight_no)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ''', [(
                                        f['airline'], 
                                        route, 
                                        window, 
                                        round(f['fare'] * 0.85, 2), 
                                        round(f['fare'] * 0.15, 2), 
                                        f['fare'], 
                                        "Yatra", 
                                        f['departure_time'], 
                                        f['flight_no']
                                    ) for f in valid_flights])  
                                    conn.commit()
                                print(f"✅ Saved {len(valid_flights)} verified records (Attempt {attempt}).")
                                break
                            else:
                                raise Exception("Zero valid flights matched route criteria.")
                                            
                        except YatraBlockException as e:
                            print(f"🛡️ Yatra Block/404 detected (Attempt {attempt}): {e}")
                            try:
                                context.close()
                            except Exception:
                                pass
                            time.sleep(3)
                            reset_profile_directory(user_data_dir)
                            if attempt == 1:
                                cooldown = random.uniform(45, 65)
                                print(f"⏳ Cooling down {round(cooldown, 1)}s before fresh session retry...")
                                time.sleep(cooldown)
                                context, page = launch_yatra_session(p, user_data_dir)
                            else:
                                # Re-open fresh session for the next window/route
                                context, page = launch_yatra_session(p, user_data_dir)

                        except Exception as e:
                            print(f"⚠️ Yatra Attempt {attempt} failed: {e}")
                            if attempt == 1:
                                time.sleep(8)
                    
                    # Human pacing between windows to avoid depleting Yatra's token bucket
                    win_jitter = random.uniform(7.0, 13.0)
                    print(f"⏳ Pacing {round(win_jitter, 1)}s before next window...")
                    time.sleep(win_jitter)

                if scraped_any_window:
                    routes_processed += 1
                    if routes_processed % 3 == 0:
                        print("\n🔄 Batch limit reached (3 routes). Rotating Yatra profile & resting...")
                        try:
                            context.close()
                        except Exception:
                            pass
                        time.sleep(3)
                        reset_profile_directory(user_data_dir)
                        time.sleep(random.uniform(15.0, 25.0))
                        context, page = launch_yatra_session(p, user_data_dir)
                    else:
                        route_jitter = random.uniform(15.0, 24.0)
                        print(f"\n⏳ Route complete. Resting {round(route_jitter, 1)}s before next route...")
                        time.sleep(route_jitter)

        finally:
            try:
                context.close()
            except Exception:
                pass

    print("\n🎉 Yatra Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_yatra_scraper()
    os._exit(0)