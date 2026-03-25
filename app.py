import streamlit as st
import pandas as pd
import requests

# --- CONFIGURATION ---
st.set_page_config(page_title="Crypto 500 Sniper", layout="wide")

def fetch_top_500_coingecko():
    """
    Fetches top 500 coins by market cap from CoinGecko.
    CoinGecko is cloud-friendly and avoids the 403/451 geoblocks.
    """
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 250, # CoinGecko max per page is 250
            "page": 1,
            "sparkline": False,
            "price_change_percentage": "24h"
        }
        
        # Fetching first 250
        response1 = requests.get(url, params=params)
        # Fetching next 250 to reach your 500 depth
        params["page"] = 2
        response2 = requests.get(url, params=params)
        
        if response1.status_code == 200 and response2.status_code == 200:
            return response1.json() + response2.json()
        else:
            st.error(f"API Error: {response1.status_code}")
            return []
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return []

# --- UI LAYOUT ---
st.title("🎯 Crypto 500 Sniper")
st.subheader("Global Momentum Scanner (Geoblock-Proof Edition)")

if st.button("Start Scan"):
    with st.spinner("Sniper is analyzing 500 assets across the global market..."):
        data = fetch_top_500_coingecko()
        
        if data:
            results = []
            for coin in data:
                change = coin.get('price_change_percentage_24h')
                price = coin.get('current_price', 0)
                volume = coin.get('total_volume', 0)
                
                # SNIPER LOGIC: Mimicking your Nifty 3%+ breakout logic
                if change and change > 3.0:
                    results.append({
                        "Ticker": coin['symbol'].upper(),
                        "Name": coin['name'],
                        "Price": f"${price:,.4f}" if price < 1 else f"${price:,.2f}",
                        "24h Change": f"{change:.2f}%",
                        "24h Volume": f"${volume:,.0f}",
                        "Signal": "🔥 BULLISH MOMENTUM"
                    })
            
            # Sort by highest gainers
            results = sorted(results, key=lambda x: float(x['24h Change'].replace('%','')), reverse=True)
            
            st.divider()
            st.write(f"### Top 5 Sniper Picks")
            
            if results:
                # Display only top 5 as requested
                df = pd.DataFrame(results[:5])
                st.table(df)
            else:
                st.warning("No 3%+ breakouts detected in the Top 500 right now.")
        
    st.success("Scan Complete.")

st.caption("Data Source: CoinGecko API (Global) | Strategy: 500-Depth Relative Strength")
