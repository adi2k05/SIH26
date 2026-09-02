import sqlite3
import pandas as pd
from datetime import datetime

def calculate_apix():
    route_weights = {
        'DEL-BOM': 0.30,
        'BLR-DEL': 0.20,
        'BLR-BOM': 0.15,
        'DEL-HYD': 0.15,
        'CCU-DEL': 0.10,
        'Other':   0.10
    }
    
    window_weights = {
        1: 0.10,
        7: 0.25,
        15: 0.35,
        30: 0.20,
        45: 0.10
    }

    print("Connecting to database...")
    conn = sqlite3.connect('airfare_index.db')
    
    df = pd.read_sql_query("SELECT * FROM raw_fares", conn)
    
    if df.empty:
        print("No data in raw_fares table to calculate index.")
        conn.close()
        return

    # Update: Group by the new 'total_fare' column
    df['total_fare'] = pd.to_numeric(df['total_fare'], errors='coerce')
    df = df.dropna(subset=['total_fare'])
    median_fares = df.groupby(['route', 'advance_window_days'])['total_fare'].median().reset_index()

    print("\n--- MEDIAN TOTAL FARES (Base + Tax) ---")
    print(median_fares)

    apix_total = 0
    for _, row in median_fares.iterrows():
        route = row['route']
        window = int(row['advance_window_days'])
        fare = float(row['total_fare'])
        
        r_weight = route_weights.get(route, route_weights['Other'])
        w_weight = window_weights.get(window, 0)
        
        apix_total += (fare * r_weight * w_weight)
    
    final_apix = round(apix_total, 2)
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    print(f"\n✅ Calculated Daily APIx for {today_date}: ₹ {final_apix}")

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