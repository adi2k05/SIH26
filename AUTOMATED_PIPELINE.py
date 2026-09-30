import concurrent.futures
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

DB_PATH = "airfare_index.db"
IST = timezone(timedelta(hours=5, minutes=30))
MAX_CONCURRENT_TERMINALS = 3

def enable_sqlite_wal():
    """Enables Write-Ahead Logging (WAL) and sets a busy timeout to prevent database lock errors when 3 scrapers write concurrently."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
    except Exception:
        pass

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

def execute_scraper(script_name, pass_type="Initial", headless=False):
    """Executes a scraper and injects headless flags dynamically."""
    env = os.environ.copy()
    if pass_type != "Initial":
        env["FORCE_RESCRAPE"] = "0"
        
    # Dynamically inject the headless toggle for individual scripts to read
    env["HEADLESS_MODE"] = "1" if headless else "0"

    creation_flags = subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0

    try:
        process = subprocess.Popen(
            [sys.executable, script_name],
            env=env,
            creationflags=creation_flags
        )
        process.wait()
        return process.returncode == 0
    except Exception as e:
        print(f"❌ Failed to execute {script_name}: {e}")
        return False

def run_worker_task(script_name, mode):
    """Worker slot: Routes execution based on run mode."""
    
    # If the user only requested a recheck ('r'), run ONE headless pass and exit.
    if mode == "r":
        print(f"🚀 [Worker Slot Acquired] Rechecking gaps for: {script_name}")
        execute_scraper(script_name, pass_type="Recheck", headless=True)
        print(f"✅ Recheck finished for {script_name}.\n")
        return script_name
        
    # Otherwise, run the standard 2-pass workflow (Initial Visible -> Recovery Headless)
    print(f"🚀 [Worker Slot Acquired] Starting: {script_name}")
    
    # 1. Primary Scrape (Visible)
    success_p1 = execute_scraper(script_name, pass_type="Initial", headless=False)
    if success_p1:
        print(f"✅ Primary run finished for {script_name}.")
    else:
        print(f"⚠️ Primary run had errors for {script_name}. Preparing immediate recovery sweep...")

    time.sleep(3)

    # 2. Immediate Gap Recheck (Headless)
    print(f"🔄 Immediate Recovery Sweep: Rechecking missing gaps for {script_name}...")
    success_p2 = execute_scraper(script_name, pass_type="Recovery", headless=True)
    if success_p2:
        print(f"🎯 Immediate recovery complete for {script_name}.")

    print(f"🔓 [Worker Slot Released] {script_name} finished both passes. Freeing slot.\n")
    return script_name

def run_pipeline():
    enable_sqlite_wal()
    today_ist, today_count, last_ts = get_today_ist_stats()
    
    print("=" * 65)
    print(f"✈️  MoSPI AirfareX Data Pipeline (Concurrent Pool Mode) | {today_ist}")
    print("=" * 65)

    choice = "fresh"
    if today_count > 0:
        print(f"ℹ️  Last recorded scrape: {last_ts} IST")
        choice = input(
            f"Data exists for today ({today_count} records). Force full re-scrape (y), Exit (n), or Recheck missing gaps (r)? (y/n/r): "
        ).strip().lower()

        if choice == "n":
            print(f"Pipeline terminated. Existing records: {today_count}.")
            return
        elif choice == "r":
            print("🔄 Recheck mode enabled. Executing exactly ONE headless gap-fill pass.")
            os.environ["FORCE_RESCRAPE"] = "0"
        elif choice == "y":
            print("⚠️  Force mode enabled. Overwriting checkpoints.")
            os.environ["FORCE_RESCRAPE"] = "1"
        else:
            print("Invalid selection. Aborting.")
            return
    else:
        print(f"Starting fresh daily collection for {today_ist}...")
        os.environ["FORCE_RESCRAPE"] = "0"

    scrapers = [
        "scraper_goibibo.py",
        "scraper_mmt.py",
        "scraper_indigo.py",
        "scraper_emt.py",
        "scraper_yatra.py",
        "scraper_airindia.py",
        "scraper_spicejet.py",
        "scraper_akasa.py",
        "scraper_ct.py",
        "scraper_ixigo.py",

    ]

    valid_scrapers = [s for s in scrapers if os.path.exists(s)]
    missing_scrapers = set(scrapers) - set(valid_scrapers)
    for m in missing_scrapers:
        print(f"⚠️  Skipping {m}: script file not found.")

    # --- PHASE 1: PARALLEL PROCESSING ---
    print("\n" + "#" * 65)
    print(f"▶ STAGE 1: Parallel Processing (Pool Capacity: {MAX_CONCURRENT_TERMINALS} Terminals)")
    print("#" * 65)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TERMINALS) as executor:
        futures = {executor.submit(run_worker_task, script, choice): script for script in valid_scrapers}
        for future in concurrent.futures.as_completed(futures):
            script = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"❌ Exception in worker thread for {script}: {e}")

    # --- IF USER SELECTED 'R', END PIPELINE HERE ---
    if choice == "r":
        _, final_count, _ = get_today_ist_stats()
        print("\n" + "=" * 65)
        print(f"🎉 Quick Recheck Complete! Total secured records: {final_count}")
        print("=" * 65)
        return

    # Subsequent passes must not force overwrite
    os.environ["FORCE_RESCRAPE"] = "0"

    _, mid_count, _ = get_today_ist_stats()
    print("\n" + "=" * 65)
    print(f"📊 Parallel Stage Complete. Total records collected so far: {mid_count}")
    print("=" * 65)

    # --- PHASE 2: FINAL UNIFIED SWEEP (SINGLE SEQUENTIAL TERMINAL) ---
    print("\n" + "#" * 65)
    print("▶ STAGE 2: Final System Sweep (Single Terminal Sequential Verification)")
    print("#" * 65)
    print("Scanning across all sources sequentially to seal any remaining route gaps...\n")

    for script in valid_scrapers:
        print(f"🔍 [Final Verification] Checking {script} in main console...")
        try:
            # Force headless mode for the final sweep directly via env vars
            env = os.environ.copy()
            env["HEADLESS_MODE"] = "1"
            subprocess.run([sys.executable, script], env=env, check=True)
            print(f"✅ Verified {script}.\n")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error during final verification of {script}: {e}\n")
        time.sleep(2)

    _, final_count, _ = get_today_ist_stats()
    print("=" * 65)
    print(f"🎉 All Pipeline Phases Complete! Total secured records: {final_count}")
    print("=" * 65)

if __name__ == "__main__":
    run_pipeline()