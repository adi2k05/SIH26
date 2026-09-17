import sqlite3

def generate_db_report():
    db_path = 'airfare_index.db'
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # 1. Overall Database Metrics
            cursor.execute("""
                SELECT 
                    COUNT(*), 
                    SUM(CASE WHEN total_fare IS NULL THEN 1 ELSE 0 END),
                    SUM(CASE WHEN departure_time IS NULL THEN 1 ELSE 0 END)
                FROM raw_fares
            """)
            total_rows, null_fares, null_dept = cursor.fetchone()
            
            print("=== OVERALL DATABASE STATS ===")
            print(f"Total Records: {total_rows}")
            print(f"Null Fares: {null_fares}")
            print(f"Null Dept Times: {null_dept}\n")
            
            # 2. Data per OTA Source
            cursor.execute("SELECT ota_source, COUNT(*) FROM raw_fares GROUP BY ota_source ORDER BY COUNT(*) DESC")
            print("=== RECORDS PER OTA SOURCE ===")
            for row in cursor.fetchall():
                print(f"{str(row[0]):<20} {row[1]}")
            print()
            
            # 3. Data per Scrape Date (Volume per day)
            # Assuming you have a 'timestamp' column. If it's named differently, update 'timestamp'
            cursor.execute("SELECT DATE(timestamp), COUNT(*) FROM raw_fares GROUP BY DATE(timestamp) ORDER BY DATE(timestamp) DESC")
            print("=== RECORDS PER SCRAPE DATE ===")
            for row in cursor.fetchall():
                print(f"{str(row[0]):<20} {row[1]}")
            print()
            
            # 4. Route Traffic (Top 20)
            cursor.execute("SELECT route, COUNT(*) FROM raw_fares GROUP BY route ORDER BY COUNT(*) DESC")
            print("=== ROUTE TRAFFIC ===")
            for row in cursor.fetchall():
                print(f"{str(row[0]):<20} {row[1]}")
            print()
            
            # 5. Data per Advance Window
            cursor.execute("SELECT advance_window_days, COUNT(*) FROM raw_fares GROUP BY advance_window_days ORDER BY advance_window_days")
            print("=== RECORDS PER ADVANCE WINDOW ===")
            for row in cursor.fetchall():
                print(f"T+{str(row[0]):<18} {row[1]}")
            print()

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")

if __name__ == "__main__":
    generate_db_report()