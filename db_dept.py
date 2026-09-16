import sqlite3

def clear_today_cleartrip_data():
    with sqlite3.connect('airfare_index.db') as conn:
        c = conn.cursor()
        c.execute("""
            DELETE FROM raw_fares 
            WHERE ota_source = 'Cleartrip' 
            AND date(timestamp) = '2026-09-16'
        """)
        conn.commit()
        print(f"🗑️ Successfully deleted {c.rowcount} Cleartrip records for September 16, 2026.")

if __name__ == "__main__":
    clear_today_cleartrip_data()