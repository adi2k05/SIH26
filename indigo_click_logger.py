import sqlite3

def clean_indigo_null_records():
    db_path = 'airfare_index.db'
    target_date = '2026-09-22'  # Today's date (IST)
    
    print("Connecting to database to clean NULL IndiGo records...")
    
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        
        # Deletes records where ota_source is 'IndiGo Direct', total_fare is NULL, and they were scraped today
        c.execute("""
            DELETE FROM raw_fares 
            WHERE ota_source = ? 
              AND total_fare IS NULL 
              AND date(timestamp) = ?
        """, ("IndiGo Direct", target_date))
        
        count = c.rowcount
        conn.commit()
        print(f"🧹 Successfully deleted {count} NULL IndiGo record(s) from {target_date}.")

if __name__ == "__main__":
    clean_indigo_null_records()