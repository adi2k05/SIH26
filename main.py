import subprocess
import sys
import time

def run_pipeline():
    scrapers = ["scraper_emt.py", "scraper_yatra.py", "scraper_spicejet.py", "scraper_akasa.py"]
    print("🚀 Starting MoSPI Airfare Data Pipeline (Sequential Mode)...")

    for script in scrapers:
        print(f"\n==========================================")
        print(f"▶ Executing {script}...")
        print(f"==========================================")
        try:
            # sys.executable ensures the script uses the active Python environment
            subprocess.run([sys.executable, script], check=True)
            print(f"✅ Finished {script} successfully.")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error while executing {script}: {e}")
            
        time.sleep(3)

    print("\n🎉 Pipeline complete! All scraper runs finished.")

if __name__ == "__main__":
    run_pipeline()