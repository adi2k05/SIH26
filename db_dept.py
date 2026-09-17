import sqlite3

def optimize_database():
    db_path = 'airfare_index.db'
    print("🔧 Starting database optimization...")
    
    with sqlite3.connect(db_path) as conn:
        # 1. Add the flight_no column safely (defaults to NULL)
        try:
            conn.execute("ALTER TABLE raw_fares ADD COLUMN flight_no TEXT;")
            print("✅ Successfully added 'flight_no' column to 'raw_fares'.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("ℹ️ 'flight_no' column already exists. Skipping creation.")
            else:
                raise e
        
        # 2. Run VACUUM to rebuild the database and shrink file size
        # SQLite requires autocommit mode (isolation_level = None) to run VACUUM
        conn.isolation_level = None
        print("🧹 Running VACUUM to reclaim space and shrink file size...")
        conn.execute("VACUUM;")
        print("✨ Database optimization and vacuum complete!")

if __name__ == "__main__":
    optimize_database()