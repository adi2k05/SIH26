import sqlite3

def keep_only_specific_date(db_path="airfare_index.db"):
    target_date = "2026-11-18"
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Delete all records where the date is NOT Nov 18, 2026
            cursor.execute("""
                DELETE FROM raw_fares 
                WHERE date(timestamp) != ?;
            """, (target_date,))
            
            deleted_rows = cursor.rowcount
            conn.commit()
            
            # Reclaim disk space
            cursor.execute("VACUUM;")
            
            print(f"✅ Successfully deleted {deleted_rows} records. Only data from {target_date} remains in 'raw_fares'.")
            
    except sqlite3.Error as e:
        print(f"❌ SQLite error: {e}")

if __name__ == "__main__":
    keep_only_specific_date()