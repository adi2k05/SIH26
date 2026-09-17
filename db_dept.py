import sqlite3

def remove_emt_sept17_data():
    # Ensure this matches the exact path to your database file
    db_path = 'airfare_index.db'
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Delete records matching the specific date and OTA source
            cursor.execute("""
                DELETE FROM raw_fares 
                WHERE ota_source = 'EaseMyTrip' 
                AND timestamp LIKE '2026-09-17%'
            """)
            
            deleted_count = cursor.rowcount
            conn.commit()
            
            print(f"✅ Successfully deleted {deleted_count} EaseMyTrip records from September 17, 2026.")
            
    except sqlite3.Error as e:
        print(f"❌ SQLite error occurred: {e}")

if __name__ == "__main__":
    remove_emt_sept17_data()