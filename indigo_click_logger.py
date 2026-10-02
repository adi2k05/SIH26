import sqlite3

def keep_only_october_records():
    with sqlite3.connect('airfare_index.db') as conn:
        cursor = conn.cursor()
        
        # Delete any records from before October 1, 2026 (clears September and older)
        cursor.execute("""
            DELETE FROM raw_fares 
            WHERE date(timestamp) < '2026-10-01'
        """)
        
        deleted_rows = cursor.rowcount
        
        # 1. Commit the deletion transaction FIRST
        conn.commit()
        
        # 2. Safely VACUUM to reclaim disk space
        cursor.execute("VACUUM")
        
        print(f"✅ Successfully deleted {deleted_rows} historical records. Only October data remains in the active airfare_index.db.")

if __name__ == "__main__":
    keep_only_october_records()