import sqlite3

def setup_database():
    conn = sqlite3.connect('airfare_index.db')
    cursor = conn.cursor()

    # Updated MoSPI Compliant Schema
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS raw_fares (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        airline TEXT,
        route TEXT,
        advance_window_days INTEGER,
        base_fare REAL,
        taxes_fees REAL,
        total_fare REAL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS daily_index (
        date DATE DEFAULT (date('now', 'localtime')),
        route TEXT,
        apix_value REAL
    )
    ''')

    conn.commit()
    conn.close()
    print("MoSPI-Compliant Database created successfully!")

if __name__ == "__main__":
    setup_database()