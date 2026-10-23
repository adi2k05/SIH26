from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from datetime import datetime, timedelta
import sqlite3
import time
import os

def is_already_scraped(route, window, source):
    if os.environ.get("FORCE_RESCRAPE") == "1":
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

def run_yatra_scraper():
    advance_windows = [1, 7, 15, 30, 45]
    top_20_routes = [
        "DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", 
        "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL", 
        "DEL-CCU", "CCU-DEL", "DEL-GOI", "BOM-GOI", 
        "DEL-MAA", "MAA-DEL", "BOM-MAA", "MAA-BOM", 
        "BLR-HYD", "HYD-BLR", "DEL-AMD", "AMD-DEL"
    ]
    
    print("Launching Yatra Multi-Route Scraper (Clean Heading Airline Extraction & Lazy-Load)...")

    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(
            headless=(os.environ.get("HEADLESS_MODE") == "1"), 
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        print("Initializing Yatra gateway session...")
        warmup = context.new_page()
        try:
            warmup.goto("https://www.yatra.com", timeout=30000)
            warmup.wait_for_timeout(3000)
        except Exception:
            pass
        finally:
            warmup.close()

        for route in top_20_routes:
            origin, dest = route.split("-")
            
            for window in advance_windows:
                if is_already_scraped(route, window, "Yatra"):
                    print(f"⏩ Yatra: {route} | T+{window} already collected today. Skipping.")
                    continue

                future_date_obj = datetime.now() + timedelta(days=window)
                date_str = future_date_obj.strftime("%d/%m/%Y")
                print(f"\n--- Yatra Scraping: {route} | T+{window} Days ({date_str}) ---")
                
                for attempt in range(1, 3):
                    page = context.new_page() 
                    try:
                        url = f"https://flight.yatra.com/air-search-ui/dom2/trigger?type=O&viewName=normal&flexi=0&noOfSegments=1&origin={origin}&originCountry=IN&destination={dest}&destinationCountry=IN&flight_depart_date={date_str}&ADT=1&CHD=0&INF=0&class=Economy&source=fresco-home"
                        page.goto(url, wait_until="domcontentloaded", timeout=50000)
                        
                        flights_loaded = False
                        for _ in range(40): 
                            try:
                                body_text = page.locator("body").inner_text()
                                if "Akamai" in body_text or "waiting" in body_text.lower():
                                    page.wait_for_timeout(1000)
                                    continue
                                if body_text.count("₹") > 4 or body_text.count("Rs") > 4:
                                    flights_loaded = True
                                    break
                            except Exception:
                                page.wait_for_timeout(1000)
                                continue
                            page.wait_for_timeout(1000)
                        
                        if not flights_loaded:
                            raise Exception("Flights not rendered after Akamai redirect.")
                            
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
                            
                        # --- JAVASCRIPT DEEP EXTRACTION ---
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
                                
                                // In the card, the first airport code is origin and the last is final destination
                                let codes = Array.from(text.matchAll(/\\(([A-Z]{{3}})\\)/g)).map(m => m[1]);
                                if (codes.length >= 2) {{
                                    cardOrig = codes[0];
                                    cardDest = codes[codes.length - 1];
                                }}
                                
                                // Fallback to legacy selectors
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
                                // Fallback to flight-id
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
                                    // Match segments: 6 chars for airports followed by airline code (2) + flight digits (3-4)
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
                                        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
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
                            page.close()
                            break
                        else:
                            raise Exception("Zero valid flights matched route criteria.")
                                        
                    except Exception as e:
                        print(f"⚠️ Yatra Attempt {attempt} failed: {e}")
                        page.close()
                        if attempt == 1:
                            time.sleep(5)
                    
                time.sleep(2)

        browser.close()
        print("\n🎉 Yatra Multi-Route Scraping Complete!")

if __name__ == "__main__":
    run_yatra_scraper()