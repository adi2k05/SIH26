import sqlite3
import time

def clean_database():
    print("Starting database vacuum. This might take 10-20 seconds...")
    start_time = time.time()
    
    with sqlite3.connect('airfare_index.db') as conn:
        # The VACUUM command rebuilds the entire database file, 
        # removing all the empty free space left behind by the deleted table.
        conn.execute("VACUUM")
        
    print(f"✅ Database successfully compressed in {round(time.time() - start_time, 2)} seconds!")
    print("Check your file size now. It should be back to normal.")

if __name__ == "__main__":
    clean_database()