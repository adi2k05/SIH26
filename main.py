import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

DB_PATH = "airfare_index.db"
IST = timezone(timedelta(hours=5, minutes=30))

def get_today_ist_stats():
    """Calculates current date in IST and queries records captured today."""
    today_ist = datetime.now(IST).strftime("%Y-%m-%d")
    
    if not os.path.exists(DB_PATH):
        return today_ist, 0, None

    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT COUNT(*), MAX(timestamp)
                FROM raw_fares
                WHERE date(timestamp) = ?
            """, (today_ist,))
            count, last_ts = c.fetchone()
            return today_ist, (count or 0), last_ts
    except Exception:
        return today_ist, 0, None

def run_pipeline():
    today_ist, today_count, last_ts = get_today_ist_stats()
    print("=" * 60)
    print(f"✈️  MoSPI AirfareX Data Pipeline | IST Date: {today_ist}")
    print("=" * 60)

    # Date match check for existing data today
    if today_count > 0:
        print(f"ℹ️  Last recorded scrape: {last_ts} IST")
        choice = input(
            f"Data already exists for today ({today_count} records). Force full re-scrape (y), Exit (n), or Recheck missing gaps (r)? (y/n/r): "
        ).strip().lower()

        if choice == "n":
            print(f"Data is already scraped for today ({today_ist}). Total records collected: {today_count}.")
            return
        elif choice == "r":
            print("🔄 Recheck mode enabled. Scanning database and scraping only missing routes...")
            os.environ["FORCE_RESCRAPE"] = "0"
        elif choice == "y":
            print("⚠️  Force mode enabled. Bypassing checkpoints for a complete overwrite...")
            os.environ["FORCE_RESCRAPE"] = "1"
        else:
            print("Invalid input. Exiting for safety.")
            return
    else:
        print(f"No records found for today ({today_ist}). Starting daily data collection...")
        os.environ["FORCE_RESCRAPE"] = "0"

    scrapers = [
       # "scraper_emt.py",
        "scraper_yatra.py",
        "scraper_spicejet.py",
        "scraper_akasa.py",
        "scraper_ct.py",
        "scraper_ixigo.py",
        "scraper_goibibo.py",
        "scraper_airindia.py",
        "scraper_mmt.py",
        "scraper_indigo.py"
    ]

    total_passes = 3
    for current_pass in range(1, total_passes + 1):
        pass_name = "Primary Extraction" if current_pass == 1 else f"Recovery Sweep {current_pass - 1}"
        print(f"\n{'#' * 60}")
        print(f"▶ PASS {current_pass}/{total_passes}: {pass_name}")
        print(f"{'#' * 60}")

        for script in scrapers:
            if not os.path.exists(script):
                print(f"⚠️  Skipping {script}: file not found.")
                continue

            print(f"\n--- Running {script} ---")
            try:
                subprocess.run([sys.executable, script], check=True)
                print(f"✅ Finished {script} without fatal errors.")
            except subprocess.CalledProcessError as e:
                print(f"❌ Error during {script}: {e}")

            time.sleep(2)

        # Ensure subsequent sweeps only fill gaps rather than overwriting
        os.environ["FORCE_RESCRAPE"] = "0"

        # Check records added after the pass
        _, updated_count, _ = get_today_ist_stats()
        print(f"\n📊 Pass {current_pass} finished. Cumulative records for today: {updated_count}")

        if current_pass < total_passes:
            print("Cooling down for 5 seconds before checking for missing route gaps...")
            time.sleep(5)

    _, final_count, _ = get_today_ist_stats()
    print("\n" + "=" * 60)
    print(f"🎉 Pipeline Complete! Total records secured for {today_ist}: {final_count}")
    print("=" * 60)

if __name__ == "__main__":
    run_pipeline()