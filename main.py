import subprocess
import time

def run_pipeline():
    # List of your standardized scraper files
    scrapers = [
        "scraper_emt.py",
        "scraper_yatra.py",
        "scraper_spicejet.py",
        "scraper_akasa.py"
    ]

    print("🚀 Starting MoSPI Airfare Index Data Pipeline...")

    for script in scrapers:
        print(f"\n========================================")
        print(f"▶ Executing {script}...")
        print(f"========================================")
        try:
            # Runs each script dynamically in the terminal
            subprocess.run(["python", script], check=True)
            print(f"✅ {script} completed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error running {script}: {e}")
        
        # 5-second cooldown to flush memory and reset network connections
        time.sleep(5)

    print("\n🎉 Full data pipeline executed! The FastAPI server can now serve updated metrics.")

if __name__ == "__main__":
    run_pipeline()