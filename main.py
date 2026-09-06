import subprocess
import time

def run_pipeline():
    scrapers = ["scraper_emt.py", "scraper_yatra.py", "scraper_spicejet.py", "scraper_akasa.py"]
    print("🚀 Starting MoSPI Airfare Data Pipeline...")

    for script in scrapers:
        print(f"▶ Executing {script}...")
        try:
            subprocess.run(["python", script], check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ Error in {script}: {e}")
        time.sleep(3)

if __name__ == "__main__":
    run_pipeline()