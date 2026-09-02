import sqlite3
import pandas as pd

# Connect to database and load into a Pandas DataFrame
conn = sqlite3.connect('airfare_index.db')
df = pd.read_sql_query("SELECT * FROM raw_fares", conn)
conn.close()

# Print the SQL table exactly as it looks
print("\n--- CURRENT DATABASE RECORDS ---")
print(df.to_string())