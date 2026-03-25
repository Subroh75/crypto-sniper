import streamlit as st
import ccxt
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Crypto 500 Sniper", layout="wide")

# Using Bybit instead of Binance to avoid 'Restricted Location' errors
exchange = ccxt.bybit()

def fetch_top_500_tickers():
    """Fetches top 500 pairs by 24h volume from Bybit"""
    try:
        # Load markets to get symbols
        exchange.load_markets()
        tickers = exchange.fetch_tickers()
        
        # Filter for USDT pairs and sort by 24h Volume
        usdt_pairs = [t for t in tickers.values() if t['symbol'].endswith('/USDT')]
        sorted_pairs = sorted(usdt_pairs, key=lambda x: x['quoteVolume'] or 0, reverse=True)
        
        return sorted_pairs[:500]
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return []

# --- UI LAYOUT ---
st.title("🎯 Crypto 500 Sniper")
st.subheader("Real-time Momentum Scanner (Powered by Bybit Data)")

if st.button("Start Scan"):
    with st.spinner("Scanning 500+ pairs for high-conviction setups..."):
        data = fetch_top_500_tickers()
        
        if data:
            results = []
            for coin in data:
                # Logic: Percentage change and last price
                change = coin.get('percentage', 0)
                price = coin.get('last', 0)
                volume = coin.get('quoteVolume', 0)
                
                # SNIPER FILTER: Up more than 3% (Bullish momentum)
                if change and change > 3.0:
                    results.append({
                        "Ticker": coin['symbol'].split(':')[0].replace('/USDT', ''),
                        "Price": f"${price:,.4f}",
                        "24h Change": f"{change:.2f}%",
                        "24h Volume": f"${volume:,.0f}",
                        "Signal": "🔥 BULLISH MOMENTUM"
                    })
            
            # Sort by highest gainers
            results = sorted(results, key=lambda x: float(x['24h Change'].replace('%','')), reverse=True)
            
            st.divider()
            st.write(f"### Top 5 Sniper Picks")
            
            if results:
                df = pd.DataFrame(results[:5])
                st.table(df)
            else:
                st.warning("No 3%+ breakouts found in the Top 500 right now.")
        
    st.success("Scan Complete.")

st.caption("Deployment Tip: If GitHub says 'File could not be edited', create a NEW file named 'crypto_sniper.py' instead.")
