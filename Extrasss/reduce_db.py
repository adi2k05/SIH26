import sqlite3

def clean_null_fares():
    # Wait up to 20 seconds for other scripts to finish their locks
    with sqlite3.connect('airfare_index.db', timeout=20.0) as conn:
        cursor = conn.cursor()
        
        # 1. Delete rows where total_fare is NULL
        cursor.execute("DELETE FROM raw_fares WHERE total_fare IS NULL")
        deleted_rows = cursor.rowcount
        
        # 2. Commit the deletion transaction FIRST
        conn.commit()
        
        # 3. Safely VACUUM to shrink the database file size
        cursor.execute("VACUUM")
        
        print(f"✅ Successfully deleted {deleted_rows} records with NULL total fares.")
        print("🧹 Database safely vacuumed and compacted.")

if __name__ == "__main__":
    clean_null_fares()