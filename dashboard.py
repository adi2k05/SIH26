import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="MoSPI Airfare Price Index (APIx)", layout="wide")
st.title("✈️ Real-time Airfare Price Index (APIx) Dashboard")
st.markdown("Developed for MoSPI | Tracking Domestic Airfare Inflation")

@st.cache_data(ttl=30)
def load_data():
    conn = sqlite3.connect('airfare_index.db')
    raw_df = pd.read_sql_query("SELECT * FROM raw_fares", conn)
    index_df = pd.read_sql_query("SELECT * FROM daily_index", conn)
    conn.close()
    return raw_df, index_df

raw_fares, daily_index = load_data()

if not daily_index.empty:
    latest_apix = daily_index.iloc[-1]['apix_value']
    
    col1, col2, col3 = st.columns(3)
    col1.metric(label="Calculated Daily APIx", value=f"₹ {latest_apix:,.2f}")
    col2.metric(label="Sectors Monitored", value="DEL-BOM")
    col3.metric(label="Total Fares Scraped", value=f"{len(raw_fares)} records")
else:
    st.warning("No index calculated yet.")

st.divider()

if not raw_fares.empty:
    # Create an interactive dropdown filter for the judges
    available_windows = sorted(raw_fares['advance_window_days'].unique())
    selected_window = st.selectbox("Select Advance Purchase Window to Inspect:", available_windows, format_func=lambda x: f"T+{x} Days")
    
    # Filter the dataframe based on the dropdown selection
    filtered_df = raw_fares[raw_fares['advance_window_days'] == selected_window]

    st.subheader(f"Raw Scraped Fares (DEL-BOM, T+{selected_window})")
    
    # Dynamic Plotly Chart
    fig = px.strip(
        filtered_df, 
        x="airline", 
        y="total_fare", 
        color="airline", 
        title=f"Ticket Price Distribution (T+{selected_window})",
        labels={"total_fare": "Total Ticket Price (₹)", "airline": "Carrier"}
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Database Records: MoSPI-Compliant Breakdown")
    st.dataframe(filtered_df[['timestamp', 'airline', 'route', 'advance_window_days', 'base_fare', 'taxes_fees', 'total_fare']], use_container_width=True)
else:
    st.info("No raw fare records found in the database.")