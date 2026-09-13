import sqlite3
import time

def fix_cleartrip_historical_fares():
    start_time = time.time()
    
    with sqlite3.connect('airfare_index.db') as conn:
        cursor = conn.cursor()
        
        # Recalculate 85/15 split for any Cleartrip row where base_fare is currently 0
        cursor.execute("""
            UPDATE raw_fares 
            SET base_fare = ROUND(total_fare * 0.85, 2),
                taxes_fees = ROUND(total_fare * 0.15, 2)
            WHERE ota_source = 'Cleartrip' 
            AND (base_fare = 0 OR base_fare = 0.0 OR base_fare IS NULL)
        """)
        
        rowcount = cursor.rowcount
        conn.commit()
        
    print(f"✅ Successfully recalculated base fare and taxes for {rowcount} Cleartrip records in {round(time.time() - start_time, 2)} seconds.")

if __name__ == "__main__":
    fix_cleartrip_historical_fares()