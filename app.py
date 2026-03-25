import streamlit as st
import ccxt
import pandas as pd
import time

# --- CONFIGURATION ---
st.set_page_config(page_title="Crypto 500 Sniper", layout="wide")

# Initialize Exchange (Binance is best for volume depth)
exchange = ccxt.binance()

def fetch_top_500_tickers():
    """Fetches top 500 pairs by 24h volume to mimic Nifty 500 depth"""
    try:
        tickers = exchange.fetch_tickers()
        # Filter for USDT pairs and sort by quoteVolume (24h Volume in USDT)
        usdt_pairs = [t for t in tickers.values() if '/USDT' in t['symbol']]
        sorted_pairs = sorted(usdt_pairs, key=lambda x: x['quoteVolume'] or 0, reverse=True)
        return sorted_pairs[:500]
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return []

# --- UI LAYOUT ---
st.title("🎯 Crypto 500 Sniper")
st.subheader("Real-time Momentum Scanner for Top 500 Crypto Assets")

if st.button("Start Scan"):
    with st.spinner("Sniper is scanning the Top 500 markets..."):
        data = fetch_top_500_tickers()
        
        if data:
            results = []
            for coin in data:
                # SNIPER LOGIC: High Volume + Price Action
                # Mimicking the logic of your Nifty volume scan
                change = coin.get('percentage', 0)
                price = coin.get('last', 0)
                volume = coin.get('quoteVolume', 0)
                
                # Filter: Looking for coins up > 3% with significant activity
                if change > 3.0:
                    results.append({
                        "Ticker": coin['symbol'].replace('/USDT', ''),
                        "Price": f"${price:,.4f}",
                        "24h Change": f"{change:.2f}%",
                        "24h Volume": f"${volume:,.0f}",
                        "Signal": "🔥 BULLISH MOMENTUM"
                    })
            
            # Sort by highest percentage change for the 'Sniper' feel
            results = sorted(results, key=lambda x: float(x['24h Change'].replace('%','')), reverse=True)
            
            st.divider()
            st.write(f"### Top 5 Sniper Picks") # As per your 5-result preference
            
            if results:
                # Display only top 5 as requested
                df = pd.DataFrame(results[:5])
                st.table(df)
            else:
                st.warning("No high-momentum setups found in the Top 500 right now.")
        
    st.success("Scan Complete.")

# --- FOOTER ---
st.caption("Logic: Scanning Top 500 USDT pairs by Volume | Data: Binance via CCXT")
