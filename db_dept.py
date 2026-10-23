import sqlite3

def delete_yatra_specific_date():
    db_file = 'airfare_index.db'
    target_date = '2026-10-23'
    target_ota = 'Yatra'
    
    print(f"Connecting to {db_file}...")
    
    # Wait up to 20 seconds to prevent "database is locked" errors
    with sqlite3.connect(db_file, timeout=20.0) as conn:
        cursor = conn.cursor()
        
        # Match the YYYY-MM-DD part of the timestamp and the specific OTA
        cursor.execute(
            "DELETE FROM raw_fares WHERE date(timestamp) = ? AND ota_source = ?", 
            (target_date, target_ota)
        )
        deleted_rows = cursor.rowcount
        
        # Commit the transaction FIRST
        conn.commit()
        
        print(f"✅ Successfully deleted {deleted_rows} records for {target_ota} on {target_date}.")
        
        # Reclaim disk space if rows were actually deleted
        if deleted_rows > 0:
            print("🧹 Vacuuming database to reclaim disk space...")
            cursor.execute("VACUUM")
            print("Database compacted.")

if __name__ == "__main__":
    delete_yatra_specific_date()