import sqlite3

def setup_database():
    # This automatically creates a file named 'airfare_index.db' in your folder
    conn = sqlite3.connect('airfare_index.db')
    cursor = conn.cursor()

    # Table 1: Stores the raw quotes exactly as the scraper finds them
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS raw_fares (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        airline TEXT,
        route TEXT,
        advance_window_days INTEGER,
        extracted_fare TEXT
    )
    ''')

    # Table 2: Stores the final calculated Airfare Price Index (APIx) for the dashboard
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS daily_index (
        date DATE DEFAULT (date('now', 'localtime')),
        route TEXT,
        apix_value REAL
    )
    ''')

    conn.commit()
    conn.close()
    print("Database created successfully! Tables are ready.")

if __name__ == "__main__":
    setup_database()