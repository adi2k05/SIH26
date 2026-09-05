import streamlit as st
import requests
import pandas as pd
import plotly.express as px

# UI Configuration
st.set_page_config(page_title="MoSPI Airfare Index", layout="wide")
st.title("✈️ MoSPI Airfare Index (APIx) Monitor")
st.write("Real-time monitoring of OTA markup variances against direct factory pricing.")

API_URL = "http://localhost:8000"

# Interactive Filters
col1, col2 = st.columns(2)
with col1:
    route = st.selectbox(
        "Select Route", 
        ["DEL-BOM", "BOM-DEL", "DEL-BLR", "BLR-DEL", "BOM-BLR", "BLR-BOM", "DEL-HYD", "HYD-DEL"]
    )
with col2:
    window = st.selectbox("Advance Purchase Window (Days)", [1, 7, 15, 30, 45], index=1)

st.divider()

# Visualization: Cross-Portal Variance
st.markdown("**OTA Markup vs. Direct Airline Pricing**")
try:
    response = requests.get(f"{API_URL}/api/fares/compare?route={route}&window={window}")
    
    if response.status_code == 200 and "comparisons" in response.json():
        df_compare = pd.DataFrame(response.json()["comparisons"])
        
        if not df_compare.empty:
            # Grouped Bar Chart to show direct comparisons
            fig = px.bar(
                df_compare, 
                x="airline", 
                y="lowest_fare", 
                color="ota_source",
                barmode="group",
                text="lowest_fare",
                labels={"lowest_fare": "Lowest Fare (₹)", "airline": "Airline Fleet", "ota_source": "Booking Portal"},
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig.update_traces(textposition='outside')
            st.plotly_chart(fig, use_container_width=True)
            
            # Raw Data Expander
            with st.expander("View Raw Comparison Data"):
                st.dataframe(df_compare, use_container_width=True)
        else:
            st.info(f"Awaiting scraper data for {route} at T+{window}.")
    else:
        st.error("Failed to fetch data. Ensure FastAPI is running.")
except requests.exceptions.ConnectionError:
    st.error("Backend offline. Run 'python api_service.py' in a separate terminal.")

st.divider()

# Macro View: System-Wide Matrix
st.markdown("**System-Wide Route Matrix (24h Average Fares)**")
try:
    res_matrix = requests.get(f"{API_URL}/api/fares/matrix")
    if res_matrix.status_code == 200 and "matrix" in res_matrix.json():
        df_matrix = pd.DataFrame(res_matrix.json()["matrix"])
        
        if not df_matrix.empty:
            # Pivot the data to create a clean matrix (Routes as rows, Windows as columns)
            pivot_df = df_matrix.pivot(index="route", columns="window", values="median_price").round(0)
            pivot_df.columns = [f"T+{col} Days" for col in pivot_df.columns]
            st.dataframe(pivot_df.style.highlight_min(axis=1, color="lightgreen"), use_container_width=True)
except Exception:
    st.warning("Matrix data unavailable.")