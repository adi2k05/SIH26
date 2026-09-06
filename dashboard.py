import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="MoSPI APIx Dashboard", layout="wide", page_icon="✈️")
st.title("✈️ Real-time Airfare Price Index (APIx)")

@st.cache_data(ttl=30)
def load_data():
    with sqlite3.connect('airfare_index.db') as conn:
        df = pd.read_sql_query("SELECT * FROM raw_fares", conn)
    if not df.empty and 'timestamp' in df.columns:
        # Convert UTC to IST (+5:30)
        df['timestamp_ist'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert('Asia/Kolkata').dt.strftime('%Y-%m-%d %I:%M %p')
    return df

df = load_data()

if df.empty:
    st.warning("⚠️ No records found in 'airfare_index.db'. Run the scrapers to populate the database.")
    st.stop()

# --- TOP METRICS BAR ---
k1, k2, k3, k4 = st.columns(4)
k1.metric("Routes Tracked", f"{df['route'].nunique()} Routes")
k2.metric("Total Records", f"{len(df):,}")
k3.metric("Data Sources", f"{df['ota_source'].nunique()} Sources")
k4.metric("Avg Industry Fare", f"₹{int(df['total_fare'].mean()):,}")

st.divider()

# --- TABS FOR WORKFLOW ---
tab_analytics, tab_heatmap, tab_raw = st.tabs(["📊 Sector Analytics", "🗺️ Sector-Window Matrix", "📋 Database Browser"])

with tab_analytics:
    f1, f2 = st.columns(2)
    selected_route = f1.selectbox("Select Route:", sorted(df['route'].unique()))
    selected_window = f2.selectbox(
        "Advance Window:", 
        sorted(df['advance_window_days'].unique()), 
        format_func=lambda x: f"T+{x} Days"
    )
    
    sub = df[(df['route'] == selected_route) & (df['advance_window_days'] == selected_window)]
    
    if not sub.empty:
        # KPI Row
        lowest_row = sub.loc[sub['total_fare'].idxmin()]
        c1, c2, c3 = st.columns(3)
        c1.metric("Cheapest Fare", f"₹{int(lowest_row['total_fare']):,}", f"{lowest_row['airline']} via {lowest_row['ota_source']}")
        c2.metric("Median Sector Fare", f"₹{int(sub['total_fare'].median()):,}")
        c3.metric("Max Sector Fare", f"₹{int(sub['total_fare'].max()):,}")
        
        # Charts
        col_left, col_right = st.columns(2)
        
        agg = sub.groupby(['airline', 'ota_source'])['total_fare'].mean().reset_index()
        fig_bar = px.bar(
            agg, x="airline", y="total_fare", color="ota_source", 
            barmode="group", text_auto=',.0f', title="Average Price by Portal & Airline",
            labels={"total_fare": "Average Fare (₹)", "airline": "Airline"}
        )
        col_left.plotly_chart(fig_bar, use_container_width=True)
        
        fig_strip = px.box(
            sub, x="airline", y="total_fare", color="ota_source",
            title="Ticket Price Distribution (Spread)",
            labels={"total_fare": "Ticket Price (₹)", "airline": "Airline"}
        )
        col_right.plotly_chart(fig_strip, use_container_width=True)
    else:
        st.info(f"No records available for {selected_route} at T+{selected_window}.")

with tab_heatmap:
    st.subheader("Cross-Sector Fare Matrix")
    matrix_df = df.groupby(['route', 'advance_window_days'])['total_fare'].mean().unstack()
    matrix_df.columns = [f"T+{c} Days" for c in matrix_df.columns]
    
    fig_heat = px.imshow(
        matrix_df, text_auto=',.0f', aspect="auto", 
        color_continuous_scale="Blues", labels=dict(color="Avg Fare (₹)")
    )
    st.plotly_chart(fig_heat, use_container_width=True)

with tab_raw:
    st.subheader("Filtered Records")
    display_cols = ['timestamp_ist', 'route', 'advance_window_days', 'airline', 'ota_source', 'base_fare', 'taxes_fees', 'total_fare']
    available_cols = [c for c in display_cols if c in df.columns]
    
    st.dataframe(df[available_cols].sort_values('timestamp_ist', ascending=False), use_container_width=True)
    
    csv = df[available_cols].to_csv(index=False).encode('utf-8')
    st.download_button("📥 Export CSV", data=csv, file_name="airfare_records.csv", mime="text/csv")