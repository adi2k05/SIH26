import sqlite3
import os

DB_PATH = "airfare_index.db"
TARGET_DATE = "2026-09-27"
OTA_SOURCE = "Cleartrip"

def clear_cleartrip_data():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database file '{DB_PATH}' not found in the current directory.")
        return

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Count records matching the criteria before deleting
            cursor.execute("""
                SELECT COUNT(*) FROM raw_fares 
                WHERE ota_source = ? AND date(timestamp) = ?
            """, (OTA_SOURCE, TARGET_DATE))
            count_before = cursor.fetchone()[0]
            
            if count_before == 0:
                print(f"ℹ️ No records found for OTA source '{OTA_SOURCE}' on date {TARGET_DATE}.")
                return

            # Execute deletion
            cursor.execute("""
                DELETE FROM raw_fares 
                WHERE ota_source = ? AND date(timestamp) = ?
            """, (OTA_SOURCE, TARGET_DATE))
            conn.commit()
            
            print(f"✅ Successfully deleted {count_before} records for '{OTA_SOURCE}' on {TARGET_DATE}.")
            
    except Exception as e:
        print(f"❌ Failed to clear database records: {e}")

if __name__ == "__main__":
    clear_cleartrip_data()