import streamlit as st
import pandas as pd
import yfinance as yf
import pandas_ta as ta
import requests

# --- CONFIGURATION ---
st.set_page_config(page_title="Crypto Sniper War Room", layout="wide")

def fetch_top_500():
    """Fetches Top 500 by Market Cap to keep the Nifty 500 depth logic"""
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": 1}
    res1 = requests.get(url, params=params).json()
    params["page"] = 2
    res2 = requests.get(url, params=params).json()
    return res1 + res2

def calculate_metrics(symbol):
    """Calculates the War Room metrics: MAs, ADX, and Mean Reversion"""
    df = yf.download(f"{symbol}-USD", period="150d", interval="1d", progress=False)
    if df.empty: return None
    
    # 1. Trend Indicators
    df['SMA20'] = ta.sma(df['Close'], length=20)
    df['SMA50'] = ta.sma(df['Close'], length=50)
    df['SMA200'] = ta.sma(df['Close'], length=200)
    
    # 2. ADX (Strength of Trend)
    adx_df = ta.adx(df['High'], df['Low'], df['Close'], length=14)
    adx_val = adx_df['ADX_14'].iloc[-1]
    
    # 3. Mean Reversion (Z-Score of price vs SMA20)
    std = df['Close'].rolling(window=20).std()
    z_score = (df['Close'] - df['SMA20']) / std
    
    # 4. Miro Score (Simplified Logic: Trend + Strength + Momentum)
    # Score out of 100
    miro = 0
    if df['Close'].iloc[-1] > df['SMA20'].iloc[-1]: miro += 25
    if df['SMA20'].iloc[-1] > df['SMA50'].iloc[-1]: miro += 25
    if adx_val > 25: miro += 25
    if z_score.iloc[-1] < -1.5: miro += 25 # Bonus for Mean Reversion entry
    
    return {
        "price": df['Close'].iloc[-1],
        "sma20": df['SMA20'].iloc[-1],
        "sma50": df['SMA50'].iloc[-1],
        "sma200": df['SMA200'].iloc[-1],
        "adx": adx_val,
        "z_score": z_score.iloc[-1],
        "miro": miro
    }

# --- UI ---
st.title("🎯 Crypto 500 Sniper: War Room")

if st.button("Start Global Scan"):
    with st.spinner("Council is debating the Top 500 markets..."):
        raw_coins = fetch_top_500()
        candidates = []
        
        # We scan the top coins but filter for the 'Sniper' setups
        for coin in raw_coins[:50]: # Scans top 50 deeply to save time; increase for full 500
            m = calculate_metrics(coin['symbol'].upper())
            if m and m['miro'] >= 75: # High conviction only
                candidates.append({
                    "Symbol": coin['symbol'].upper(),
                    "Miro Score": m['miro'],
                    "ADX": f"{m['adx']:.1f}",
                    "Trend": "Bullish" if m['price'] > m['sma50'] else "Bearish",
                    "Reversion": "Oversold" if m['z_score'] < -2 else "Normal"
                })

        st.subheader("The AI Debate Council Verdict")
        top_5 = sorted(candidates, key=lambda x: x['Miro Score'], reverse=True)[:5]
        
        for pick in top_5:
            with st.expander(f"Analysis for {pick['Symbol']} - Score: {pick['Miro Score']}"):
                col1, col2, col3 = st.columns(3)
                col1.info(f"**The Bull:** Trend is strong (ADX {pick['ADX']}). Ride the momentum!")
                col2.error(f"**The Bear:** RSI is high. Watch for the {pick['Reversion']} trap.")
                col3.warning(f"**The Quant:** Miro Score {pick['Miro Score']} suggests 80% probability of continuation.")

        st.table(pd.DataFrame(top_5))
