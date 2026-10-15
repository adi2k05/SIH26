import sqlite3

def force_db_cleanup():
    print("Forcing SQLite to merge WAL data and clean up...")
    with sqlite3.connect('airfare_index.db') as conn:
        # TRUNCATE forces the WAL file to commit all data to the main DB and shrink to 0 bytes
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        conn.commit()
    print("Database safely consolidated.")

if __name__ == "__main__":
    force_db_cleanup()