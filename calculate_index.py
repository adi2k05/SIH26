import sqlite3
import pandas as pd
from datetime import datetime

def calculate_apix():
    # 1. DGCA Passenger Traffic Weights (Hackathon Estimates)
    route_weights = {
        'DEL-BOM': 0.30,
        'BLR-DEL': 0.20,
        'BLR-BOM': 0.15,
        'DEL-HYD': 0.15,
        'CCU-DEL': 0.10,
        'Other':   0.10
    }
    
    # 2. Advance-Purchase Window Weights
    window_weights = {
        1: 0.10,
        7: 0.25,
        15: 0.35,
        30: 0.20,
        45: 0.10
    }

    print("Connecting to database...")
    conn = sqlite3.connect('airfare_index.db')
    
    # Load data into Pandas
    df = pd.read_sql_query("SELECT * FROM raw_fares", conn)
    
    if df.empty:
        print("No data in raw_fares table to calculate index.")
        conn.close()
        return

    # Fix: Explicitly cast extracted_fare from TEXT to numeric
    df['extracted_fare'] = pd.to_numeric(df['extracted_fare'], errors='coerce')
    df = df.dropna(subset=['extracted_fare'])

    # 3. Calculate Median Fare per Route and Window
    median_fares = df.groupby(['route', 'advance_window_days'])['extracted_fare'].median().reset_index()

    print("\n--- MEDIAN FARES ---")
    print(median_fares)

    # 4. Calculate the Weighted APIx
    apix_total = 0
    
    for _, row in median_fares.iterrows():
        route = row['route']
        window = int(row['advance_window_days'])
        fare = float(row['extracted_fare'])
        
        r_weight = route_weights.get(route, route_weights['Other'])
        w_weight = window_weights.get(window, 0)
        
        apix_total += (fare * r_weight * w_weight)
    
    final_apix = round(apix_total, 2)
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    print(f"\n✅ Calculated Daily APIx for {today_date}: ₹ {final_apix}")

    # 5. Save Calculated Index to daily_index table
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO daily_index (date, route, apix_value)
        VALUES (?, ?, ?)
    ''', (today_date, "AGGREGATED_NATIONAL", final_apix))
    
    conn.commit()
    conn.close()
    print("Daily Index saved to database successfully.")

if __name__ == "__main__":
    calculate_apix()