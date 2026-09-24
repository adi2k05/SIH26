import sqlite3

def cleanup_mmt_data():
    db_name = 'airfare_index.db'
    target_date = '2026-09-24'
    target_ota = 'MakeMyTrip'

    print(f"Scanning for errored {target_ota} records on {target_date}...")

    try:
        with sqlite3.connect(db_name) as conn:
            c = conn.cursor()
            
            # Check how many records match the criteria before deleting
            c.execute("""
                SELECT COUNT(*) FROM raw_fares 
                WHERE ota_source = ? AND date(timestamp) = ?
            """, (target_ota, target_date))
            
            count = c.fetchone()[0]
            
            if count > 0:
                # Perform the deletion
                c.execute("""
                    DELETE FROM raw_fares 
                    WHERE ota_source = ? AND date(timestamp) = ?
                """, (target_ota, target_date))
                conn.commit()
                print(f"✅ Successfully deleted {count} records.")
            else:
                print("ℹ️ No matching records found. Database is already clean.")
                
    except sqlite3.OperationalError as e:
        print(f"⚠️ Database error: {e} (The table might not exist yet).")
    except Exception as e:
        print(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    cleanup_mmt_data()