import sqlite3
import os

def clean_november_database():
    db_file = 'airfare_index.db'
    
    if not os.path.exists(db_file):
        print(f"Error: Database file '{db_file}' not found in the current directory.")
        return

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM raw_fares")
        initial_count = cursor.fetchone()[0]
        print(f"Total records before cleanup: {initial_count}")
        
        cursor.execute("SELECT COUNT(*) FROM raw_fares WHERE timestamp NOT LIKE '2026-11-%'")
        mistake_count = cursor.fetchone()[0]
        print(f"Found {mistake_count} records that do not belong to November 2026.")
        
        if mistake_count == 0:
            print("No stray records found. Database is already clean.")
            return

        delete_query = "DELETE FROM raw_fares WHERE timestamp NOT LIKE '2026-11-%'"
        cursor.execute(delete_query)
        
        conn.commit()
        deleted_count = cursor.rowcount
        print(f"✅ Successfully deleted {deleted_count} stray records (including October data).")
        
        cursor.execute("SELECT COUNT(*) FROM raw_fares")
        final_count = cursor.fetchone()[0]
        print(f"Total records remaining (Strictly November): {final_count}")
        
        print("🧹 Vacuuming database to reclaim disk space...")
        conn.execute("VACUUM")
        print("Done!")
        
    except sqlite3.Error as e:
        print(f"❌ A database error occurred: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    clean_november_database()