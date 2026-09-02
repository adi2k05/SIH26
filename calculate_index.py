import sqlite3
import pandas as pd
from datetime import datetime

def calculate_apix():
    # 1. DGCA Passenger Traffic Weights (Hackathon Estimates)
    # Delhi-Mumbai is the busiest route in India, so it gets the highest weight
    route_weights = {
        'DEL-BOM': 0.30,
        'BLR-DEL': 0.20,
        'BLR-BOM': 0.15,
        'DEL-HYD': 0.15,
        'CCU-DEL': 0.10,
        'Other':   0.10
    }
    
    # 2. Advance-Purchase Window Weights (Industry Standard Booking Curves)
    window_weights = {
        1: 0.10,  # Last minute (low volume, high price)
        7: 0.25,
        15: 0.35, # Peak booking window
        30: 0.20,
        45: 0.10
    }

    print("Connecting to database...")
    conn = sqlite3.connect('airfare_index.db')
    
    # Load all scraped fares into a Pandas DataFrame
    df = pd.read_sql_query("SELECT * FROM raw_fares", conn)
    
    if df.empty:
        print("No data in raw_fares table to calculate index.")
        return

    # 3. Calculate Median Fare per Route and Window
    # We use median to drop extreme outliers (like a random ₹1,00,000 first-class glitch)
    median_fares = df.groupby(['route', 'advance_window_days'])['extracted_fare'].median().reset_index()

    print("\n--- MEDIAN FARES ---")
    print(median_fares)

    # 4. Calculate the Weighted APIx for the Day
    apix_total = 0
    
    for _, row in median_fares.iterrows():
        route = row['route']
        window = row['advance_window_days']
        fare = row['extracted_fare']
        
        r_weight = route_weights.get(route, route_weights['Other'])
        w_weight = window_weights.get(window, 0)
        
        # Weighted contribution of this specific fare bracket
        apix_total += (fare * r_weight * w_weight)
    
    # Baseline normalization (e.g., dividing by an arbitrary base-period constant if required)
    # For now, we represent the index as the true weighted average ticket price.
    final_apix = round(apix_total, 2)
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    print(f"\n✅ Calculated Daily APIx for {today_date}: ₹ {final_apix}")

    # 5. Save the Calculated Index to the Database for the Dashboard
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO daily_index (date, route, apix_value)
        VALUES (?, ?, ?)
    ''', (today_date, "AGGREGATED_NATIONAL", final_apix))
    
    conn.commit()
    conn.close()
    print("Daily Index saved to database.")

if __name__ == "__main__":
    calculate_apix()