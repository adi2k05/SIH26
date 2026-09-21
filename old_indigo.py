import sqlite3

def clean_stale_ixigo_data():
    conn = sqlite3.connect('airfare_index.db')
    cursor = conn.cursor()
    
    # Target Ixigo records created on Sept 21, 2026
    cursor.execute("""
        DELETE FROM raw_fares 
        WHERE ota_source = 'Ixigo' 
        AND date(timestamp) = '2026-09-21'
    """)
    
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"🧹 Cleaned up {deleted_rows} stale Ixigo records from September 21, 2026.")

if __name__ == "__main__":
    clean_stale_ixigo_data()