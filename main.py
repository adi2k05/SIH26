import subprocess
import sys
import time
import os

def run_pipeline():
    print("🚀 Starting MoSPI Airfare Data Pipeline...")
    
    # Interactive Hard-Override Toggle
    choice = input("Do you want to FORCE a re-scrape for today? (y/n): ").strip().lower()
    if choice == 'y':
        print("⚠️ FORCE MODE ENABLED: Bypassing checkpoints...")
        os.environ["FORCE_RESCRAPE"] = "1"
    else:
        os.environ["FORCE_RESCRAPE"] = "0"

    scrapers = ["scraper_emt.py", "scraper_yatra.py", "scraper_spicejet.py", "scraper_akasa.py"]

    for script in scrapers:
        print(f"\n==========================================")
        print(f"▶ Executing {script}...")
        print(f"==========================================")
        try:
            subprocess.run([sys.executable, script], check=True)
            print(f"✅ Finished {script} successfully.")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error while executing {script}: {e}")
            
        time.sleep(3)

    print("\n🎉 Pipeline complete! All scraper runs finished.")

if __name__ == "__main__":
    run_pipeline()