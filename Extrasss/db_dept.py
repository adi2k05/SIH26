import sqlite3

def copy_specific_date_data():
    target_db = 'airfare_index.db'
    source_db = '24data.db'
    target_date = '2026-10-24'

    print(f"Attaching {source_db} to {target_db}...")
    
    with sqlite3.connect(target_db, timeout=20.0) as conn:
        cursor = conn.cursor()
        
        # Attach the source database so we can query both simultaneously
        cursor.execute(f"ATTACH DATABASE '{source_db}' AS source_db")
        
        # Insert records directly from the attached database
        cursor.execute(f"""
            INSERT INTO main.raw_fares (
                timestamp, airline, route, advance_window_days, 
                base_fare, taxes_fees, total_fare, ota_source, 
                departure_time, flight_no
            )
            SELECT 
                timestamp, airline, route, advance_window_days, 
                base_fare, taxes_fees, total_fare, ota_source, 
                departure_time, flight_no
            FROM source_db.raw_fares
            WHERE date(timestamp) = ?
        """, (target_date,))
        
        copied_rows = cursor.rowcount
        conn.commit()
        
        print(f"✅ Successfully copied {copied_rows} records for {target_date} from {source_db} to {target_db}.")

if __name__ == "__main__":
    copy_specific_date_data()