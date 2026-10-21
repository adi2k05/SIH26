import sqlite3

def keep_only_specific_date_records():
    db_file = 'airfare_index.db'
    target_date = '2026-10-21'
    
    print(f"Connecting to {db_file}...")
    
    # Wait up to 20 seconds to prevent "database is locked" errors
    with sqlite3.connect(db_file, timeout=20.0) as conn:
        cursor = conn.cursor()
        
        # Delete all rows where the date does NOT match the target date
        # (or where the timestamp is missing/NULL)
        cursor.execute(
            "DELETE FROM raw_fares WHERE date(timestamp) != ? OR timestamp IS NULL", 
            (target_date,)
        )
        deleted_rows = cursor.rowcount
        
        # Commit the deletion transaction FIRST before vacuuming
        conn.commit()
        
        print(f"✅ Successfully deleted {deleted_rows} records that were NOT from {target_date}.")
        
        if deleted_rows > 0:
            print("🧹 Vacuuming database to reclaim disk space...")
            cursor.execute("VACUUM")
            print("Database compacted.")

if __name__ == "__main__":
    keep_only_specific_date_records()