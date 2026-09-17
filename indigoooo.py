#!/usr/bin/env python3
"""
IndiGo fare scraper  ->  Python list of dicts

Each record uses the same fields as your raw_fares table, so a DB insert later is one line:
  {"timestamp", "airline", "route", "advance_window", "base_fare",
   "taxes_fees", "total_fare", "ota_source", "departure_time"}
A failed lookup adds one record with None fares (same as the NULL rows in your DB).

Setup:
  pip install playwright
  playwright install chromium

Usage:
  python indigo_scraper.py --headful                 # one pass, visible browser, prints the list
  python indigo_scraper.py --json results.json       # also save the list to a JSON file
  python indigo_scraper.py --discover                # you search manually; dumps API JSON to ./captures
  python indigo_scraper.py --parse captures/007.json --date 2026-10-30   # test parser offline

From your own code:
  from indigo_scraper import scrape_all
  records = scrape_all()          # -> list[dict]
"""
import argparse
import asyncio
import json
import logging
import random
import re
import time
from datetime import date as Date, datetime, timedelta
from pathlib import Path

# ============================== CONFIG ==============================
AIRLINE = "IndiGo"
OTA_SOURCE = "IndiGo Direct"

ROUTES = ["AMD-DEL", "DEL-AMD", "HYD-BLR", "BLR-HYD", "MAA-BOM", "BOM-MAA"]
ADVANCE_WINDOWS = [45, 30, 15, 7, 1]

# "cheapest"    -> T1/T2/T3 = 3 cheapest fares that day
# "time_of_day" -> T1 = dep before 12:00, T2 = 12:00-17:59, T3 = 18:00+, cheapest in each band
SLOT_MODE = "cheapest"

# Only used when the API response has no base/tax breakdown (matches your SpiceJet 85/15 split).
TAX_SHARE_ESTIMATE = 0.15

HOME_URL = "https://www.goindigo.in/"
API_HOST_HINT = "goindigo"                              # booking API host contains this
API_PATH_HINTS = ("search", "availability", "flight")   # verify with --discover
SEARCH_TIMEOUT_S = 35
DELAY_BETWEEN_SEARCHES = (8, 15)    # seconds; keep it slow and polite
CAPTURE_DIR = Path("captures")

# Form selectors: best guesses. Confirm in DevTools on the live site and edit here.
SEL = {
    "from_field":  "input[placeholder*='From' i], [aria-label*='From' i]",
    "to_field":    "input[placeholder*='To' i], [aria-label*='To' i]",
    "city_option": "[role='option']:has-text('{code}'), li:has-text('{code}')",
    "date_field":  "[aria-label*='Departure' i], input[placeholder*='Departure' i]",
    "next_month":  "button[aria-label*='next' i]",
    "search_btn":  "button:has-text('Search')",
    "popup_close": "button:has-text('Accept'), button[aria-label*='close' i]",
}
# ====================================================================

log = logging.getLogger("indigo")


# --------------------------- PARSING -------------------------------
DEP_KEY = re.compile(r"^(std|departure|departuredate|departuretime|departuredatetime)$", re.I)
TOTAL_KEY = re.compile(r"^(totalfare|totalamount|totalprice|publishedfare|farewithtax|"
                       r"grandtotal|totalfareamount)$", re.I)
BASE_KEY = re.compile(r"^(basefare|fareamount|baseprice|baseamount)$", re.I)
TAX_KEY = re.compile(r"^(tax|taxes|taxamount|totaltax|totaltaxes|taxesandfees|taxandfees)$", re.I)
DT_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})")


def _dt(s):
    m = DT_RE.search(s) if isinstance(s, str) else None
    return datetime.strptime(f"{m[1]} {m[2]}:{m[3]}", "%Y-%m-%d %H:%M") if m else None


def _num(v, lo, hi):
    if isinstance(v, dict):  # e.g. {"totalFare": {"amount": 6365}}
        v = next((v[k] for k in ("amount", "value", "total") if k in v), None)
    try:
        x = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return x if lo <= x <= hi else None


def _collect(node, pattern, lo, hi, acc):
    """Append (value, parent_dict) for every key matching pattern in the subtree."""
    if isinstance(node, dict):
        for k, v in node.items():
            if pattern.match(k):
                n = _num(v, lo, hi)
                if n is not None:
                    acc.append((n, node))
            if isinstance(v, (dict, list)):
                _collect(v, pattern, lo, hi, acc)
    elif isinstance(node, list):
        for v in node:
            _collect(v, pattern, lo, hi, acc)
    return acc


def _dep_of(node):
    """Departure datetime on this dict, or one level down (e.g. designator.departure, segments[0].std)."""
    candidates = [node]
    for v in node.values():
        if isinstance(v, dict):
            candidates.append(v)
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            candidates.append(v[0])
    for c in candidates:
        for k, v in c.items():
            if DEP_KEY.match(k) and _dt(v):
                return _dt(v)
    return None


def _best_fare(node):
    totals = _collect(node, TOTAL_KEY, 300, 300000, [])
    if not totals:
        return None
    total, parent = min(totals, key=lambda h: h[0])
    base = next((n for n, _ in _collect(parent, BASE_KEY, 0, 300000, [])), None)
    tax = next((n for n, _ in _collect(parent, TAX_KEY, 0, 300000, [])), None)
    if base is not None and tax is None:
        tax = round(total - base, 2)
    elif tax is not None and base is None:
        base = round(total - tax, 2)
    return {"total": total, "base": base, "tax": tax}


def extract_fares(payload, travel_date: Date):
    """Find the innermost objects that carry both a departure datetime and a fare."""
    found = {}

    def walk(node):
        hit = False
        if isinstance(node, dict):
            for v in node.values():
                hit |= walk(v)
            if not hit:
                dep = _dep_of(node)
                if dep and dep.date() == travel_date:
                    fare = _best_fare(node)
                    if fare:
                        key = dep.strftime("%H:%M")
                        if key not in found or fare["total"] < found[key]["total"]:
                            found[key] = {**fare, "dep": dep}
                        hit = True
        elif isinstance(node, list):
            for v in node:
                hit |= walk(v)
        return hit

    walk(payload)
    return list(found.values())


def assign_slots(fares):
    if SLOT_MODE == "cheapest":
        return list(zip(("T1", "T2", "T3"), sorted(fares, key=lambda f: f["total"])[:3]))
    bands = {"T1": (0, 12), "T2": (12, 18), "T3": (18, 24)}
    out = []
    for slot, (lo, hi) in bands.items():
        band = [f for f in fares if lo <= f["dep"].hour < hi]
        if band:
            out.append((slot, min(band, key=lambda f: f["total"])))
    return out


def build_records(route, window, fares):
    """Turn parsed fares into records shaped like raw_fares rows."""
    base_rec = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "airline": AIRLINE,
        "route": route,
        "advance_window": window,
        "ota_source": OTA_SOURCE,
    }
    if not fares:
        return [{**base_rec, "base_fare": None, "taxes_fees": None,
                 "total_fare": None, "departure_time": None}]
    records = []
    for slot, f in assign_slots(fares):
        total, base, tax = round(f["total"], 2), f["base"], f["tax"]
        if base is None or tax is None:
            tax = round(total * TAX_SHARE_ESTIMATE, 2)
            base = round(total - tax, 2)
        records.append({**base_rec, "base_fare": base, "taxes_fees": tax,
                        "total_fare": total, "departure_time": slot})
    return records


# --------------------------- BROWSER -------------------------------
async def dismiss_popups(page):
    try:
        await page.locator(SEL["popup_close"]).first.click(timeout=3000)
    except Exception:
        pass


async def pick_city(page, field_sel, code):
    await page.locator(field_sel).first.click()
    await page.keyboard.type(code, delay=120)
    opt = page.locator(SEL["city_option"].format(code=code)).first
    await opt.wait_for(timeout=10000)
    await opt.click()


async def pick_date(page, d: Date):
    await page.locator(SEL["date_field"]).first.click()
    labels = [
        f"{d:%A}, {d:%B} {d.day}, {d.year}",
        f"{d:%B} {d.day}, {d.year}",
        f"{d.day} {d:%B} {d.year}",
        d.isoformat(),
    ]
    for _ in range(3):  # 45 days out can need two month flips
        for lab in labels:
            loc = page.locator(f"[aria-label*='{lab}'], [data-date='{d.isoformat()}']").first
            if await loc.count():
                await loc.click()
                return
        await page.locator(SEL["next_month"]).first.click()
        await page.wait_for_timeout(500)
    raise RuntimeError(f"date {d} not found in picker")


async def scrape_one(context, route, window):
    origin, dest = route.split("-")
    travel_date = (datetime.now() + timedelta(days=window)).date()
    payloads = []

    async def on_response(resp):
        url = resp.url.lower()
        if API_HOST_HINT not in url or not any(h in url for h in API_PATH_HINTS):
            return
        if "json" not in (resp.headers.get("content-type") or ""):
            return
        try:
            payloads.append(await resp.json())
        except Exception:
            pass

    page = await context.new_page()
    page.on("response", on_response)
    try:
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
        await dismiss_popups(page)
        await pick_city(page, SEL["from_field"], origin)
        await pick_city(page, SEL["to_field"], dest)
        await pick_date(page, travel_date)
        await page.locator(SEL["search_btn"]).first.click()

        deadline = time.monotonic() + SEARCH_TIMEOUT_S
        while time.monotonic() < deadline:
            await asyncio.sleep(1)
            fares = extract_fares(payloads, travel_date)
            if fares:
                return fares
        raise RuntimeError("no fare JSON captured before timeout")
    except Exception as e:
        log.warning("%s w=%s failed: %s", route, window, e)
        CAPTURE_DIR.mkdir(exist_ok=True)
        try:
            await page.screenshot(path=str(CAPTURE_DIR / f"fail_{route}_{window}.png"))
        except Exception:
            pass
        return []
    finally:
        await page.close()


async def scrape_all_async(headful=False, routes=None, windows=None):
    """Scrape every route/window and return a list of records."""
    from playwright.async_api import async_playwright

    records = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headful)
        context = await browser.new_context(
            locale="en-IN", timezone_id="Asia/Kolkata", viewport={"width": 1366, "height": 900}
        )
        for route in routes or ROUTES:
            for window in windows or ADVANCE_WINDOWS:
                fares = await scrape_one(context, route, window)
                new = build_records(route, window, fares)
                records.extend(new)
                log.info("%s w=%-2s -> %s", route, window,
                         ", ".join(f"{r['departure_time']}={r['total_fare']:.0f}" for r in new)
                         if fares else "None")
                await asyncio.sleep(random.uniform(*DELAY_BETWEEN_SEARCHES))
        await browser.close()
    return records


def scrape_all(headful=False, routes=None, windows=None):
    """Sync wrapper: records = scrape_all()"""
    return asyncio.run(scrape_all_async(headful, routes, windows))


# --------------------------- DEBUG TOOLS ---------------------------
async def discover():
    """Open a browser, let you search by hand, and save every JSON response from IndiGo."""
    from playwright.async_api import async_playwright

    CAPTURE_DIR.mkdir(exist_ok=True)
    n = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await (await browser.new_context(locale="en-IN")).new_page()

        async def on_response(resp):
            nonlocal n
            if API_HOST_HINT not in resp.url or "json" not in (resp.headers.get("content-type") or ""):
                return
            try:
                body = await resp.json()
            except Exception:
                return
            n += 1
            out = CAPTURE_DIR / f"{n:03d}.json"
            out.write_text(json.dumps({"url": resp.url, "method": resp.request.method, "body": body}, indent=2))
            print(f"[{n:03d}] {resp.request.method} {resp.url}")

        page.on("response", on_response)
        await page.goto(HOME_URL)
        print("Run a one-way search in the browser window, then close it.")
        await page.wait_for_event("close", timeout=0)
        await browser.close()


def parse_file(path, date_str):
    data = json.loads(Path(path).read_text())
    body = data.get("body", data)
    fares = extract_fares(body, datetime.strptime(date_str, "%Y-%m-%d").date())
    for f in sorted(fares, key=lambda f: f["dep"]):
        print(f"{f['dep']:%H:%M}  total={f['total']:.0f}  base={f['base']}  tax={f['tax']}")
    print(f"\n{len(fares)} fares found. Records that would be created:")
    for r in build_records("TEST-RUN", 0, fares):
        print(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headful", action="store_true", help="show the browser")
    ap.add_argument("--json", metavar="FILE", help="also save the list to a JSON file")
    ap.add_argument("--discover", action="store_true", help="capture API JSON during a manual search")
    ap.add_argument("--parse", metavar="FILE", help="test the parser on a captured JSON file")
    ap.add_argument("--date", help="travel date for --parse (YYYY-MM-DD)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.discover:
        return asyncio.run(discover())
    if args.parse:
        if not args.date:
            ap.error("--parse needs --date")
        return parse_file(args.parse, args.date)

    records = scrape_all(headful=args.headful)

    print(f"\n{len(records)} records")
    for r in records:
        print(r)
    if args.json:
        Path(args.json).write_text(json.dumps(records, indent=2))
        print(f"saved to {args.json}")


if __name__ == "__main__":
    main()
