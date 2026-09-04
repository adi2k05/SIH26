import sqlite3
import pandas as pd

def calculate_apix():
    # Adding a generic weight system to accommodate the expanded routes
    route_weights = {
        'DEL-BOM': 0.15, 'BOM-DEL': 0.15, 
        'DEL-BLR': 0.10, 'BLR-DEL': 0.10,
        'BOM-BLR': 0.05, 'BLR-BOM': 0.05,
        'DEL-HYD': 0.05, 'HYD-DEL': 0.05,
        'DEL-CCU': 0.05, 'CCU-DEL': 0.05,
        'Other':   0.02
    }
    window_weights = {1: 0.10, 7: 0.25, 15: 0.35, 30: 0.20, 45: 0.10}

    print("Connecting to database...")
    conn = sqlite3.connect('airfare_index.db')
    
    # 1. Extract the actual Date the scraper ran (ignoring exact hour/minute)
    df = pd.read_sql_query("SELECT *, date(timestamp) as collection_date FROM raw_fares", conn)
    
    if df.empty:
        print("No data in raw_fares.")
        conn.close()
        return

    df['total_fare'] = pd.to_numeric(df['total_fare'], errors='coerce')
    df = df.dropna(subset=['total_fare'])
    
    # 2. Group by Collection Date, Route, and Window
    median_fares = df.groupby(['collection_date', 'route', 'advance_window_days'])['total_fare'].median().reset_index()

    cursor = conn.cursor()
    unique_dates = median_fares['collection_date'].unique()
    
    # 3. Calculate an APIx for EVERY specific scraping day
    for scrape_date in unique_dates:
        daily_data = median_fares[median_fares['collection_date'] == scrape_date]
        apix_total = 0
        
        for _, row in daily_data.iterrows():
            route = row['route']
            window = int(row['advance_window_days'])
            fare = float(row['total_fare'])
            
            r_weight = route_weights.get(route, route_weights['Other'])
            w_weight = window_weights.get(window, 0)
            
            apix_total += (fare * r_weight * w_weight)
        
        final_apix = round(apix_total, 2)
        
        # Delete existing calculation for this specific date to prevent duplicates if you run it twice
        cursor.execute("DELETE FROM daily_index WHERE date = ?", (scrape_date,))
        cursor.execute('''
            INSERT INTO daily_index (date, route, apix_value)
            VALUES (?, ?, ?)
        ''', (scrape_date, "AGGREGATED_NATIONAL", final_apix))
        
        print(f"✅ Calculated APIx for {scrape_date}: ₹ {final_apix}")

    conn.commit()
    conn.close()
    print("Backtest processing complete.")

if __name__ == "__main__":
    calculate_apix()