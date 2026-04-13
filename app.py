from __future__ import annotations

import io
import json
import threading
import time
from dataclasses import dataclass
from typing import Dict, Any

import pandas as pd
import streamlit as st
import websocket

# =========================================================
# CONFIG
# =========================================================
st.set_page_config(layout="wide")
KRAKEN_WS_URL = "wss://ws.kraken.com/v2"

# =========================================================
# GLOBAL STATE (WebSocket buffer)
# =========================================================
if "price_data" not in st.session_state:
    st.session_state.price_data = []

if "connected" not in st.session_state:
    st.session_state.connected = False

# =========================================================
# WEBSOCKET CLIENT
# =========================================================
def start_ws(symbol="BTC/USD"):
    def on_message(ws, message):
        msg = json.loads(message)

        if "channel" in msg and msg["channel"] == "ticker":
            data = msg["data"][0]
            price = float(data["last"])
            volume = float(data["volume"])

            st.session_state.price_data.append({
                "price": price,
                "volume": volume,
                "time": time.time()
            })

            # keep last 200 points
            st.session_state.price_data = st.session_state.price_data[-200:]

    def on_open(ws):
        subscribe = {
            "method": "subscribe",
            "params": {
                "channel": "ticker",
                "symbol": [symbol]
            }
        }
        ws.send(json.dumps(subscribe))
        st.session_state.connected = True

    ws = websocket.WebSocketApp(
        KRAKEN_WS_URL,
        on_message=on_message,
        on_open=on_open,
    )

    ws.run_forever()


# start WS only once
if "ws_thread" not in st.session_state:
    t = threading.Thread(target=start_ws, daemon=True)
    t.start()
    st.session_state.ws_thread = t


# =========================================================
# COMPUTE ENGINE
# =========================================================
def compute_signals(df: pd.DataFrame):
    if len(df) < 10:
        return None

    price_series = df["price"]
    volume_series = df["volume"]

    last_price = price_series.iloc[-1]

    # volume score
    vol_ratio = volume_series.iloc[-10:].mean() / max(volume_series.mean(), 1)
    volume_score = min(5, vol_ratio * 2)

    # price expansion
    returns = price_series.pct_change()
    price_score = min(5, returns.abs().iloc[-10:].mean() * 100)

    # trend
    ma_short = price_series.rolling(5).mean().iloc[-1]
    ma_long = price_series.rolling(15).mean().iloc[-1]
    trend_score = 3 if ma_short > ma_long else 1

    # range
    high = price_series.max()
    low = price_series.min()
    range_score = ((last_price - low) / (high - low)) * 2 if high != low else 1

    # volatility
    volatility = returns.std() * 10

    # slope
    slope = returns.iloc[-5:].mean() * 50

    # breakout
    breakout = range_score / 2

    return {
        "price": last_price,
        "volume_score": volume_score,
        "price_score": price_score,
        "trend_score": trend_score,
        "range_score": range_score,
        "volatility": volatility,
        "slope": slope,
        "breakout": breakout,
    }


# =========================================================
# UI HELPERS
# =========================================================
def section(title):
    st.markdown(f"## {title}")

def card(label, value):
    st.metric(label, value)

# =========================================================
# MAIN UI
# =========================================================
st.title("Crypto AI Lab (Live Engine)")

symbol = st.selectbox("Symbol", ["BTC/USD", "ETH/USD"])

df = pd.DataFrame(st.session_state.price_data)

if df.empty:
    st.warning("Waiting for live data...")
    st.stop()

signals = compute_signals(df)

if not signals:
    st.warning("Collecting data...")
    st.stop()

# =========================================================
# 1. SIGNAL OUTPUT
# =========================================================
section("Signal Output")

signal_strength = signals["volume_score"] + signals["price_score"] + signals["trend_score"]

if signal_strength > 10:
    signal_label = "High Momentum"
elif signal_strength > 6:
    signal_label = "Constructive"
else:
    signal_label = "Weak"

st.success(signal_label)

# =========================================================
# 2. SIGNAL COMPONENTS
# =========================================================
section("Signal Components")

cols = st.columns(5)
cols[0].metric("Volume", f"{signals['volume_score']:.2f}/5")
cols[1].metric("Price", f"{signals['price_score']:.2f}/5")
cols[2].metric("Trend", f"{signals['trend_score']}/3")
cols[3].metric("Range", f"{signals['range_score']:.2f}/2")
cols[4].metric("Volatility", f"{signals['volatility']:.2f}")

# =========================================================
# 3. MARKET STRUCTURE
# =========================================================
section("Market Structure")

if signals["trend_score"] >= 2:
    structure = "Bullish"
elif signals["trend_score"] <= 1:
    structure = "Bearish"
else:
    structure = "Sideways"

st.info(structure)

# =========================================================
# 4. TIMING QUALITY
# =========================================================
section("Timing Quality")

if signals["breakout"] > 0.7:
    timing = "High-quality setup"
elif signals["breakout"] > 0.4:
    timing = "Good setup"
else:
    timing = "Low-quality setup"

st.info(timing)

# =========================================================
# 5. AI LAB
# =========================================================
section("AI Lab")

st.write(f"""
**Market Analyst**  
{structure} structure with momentum score {signal_strength:.2f}

**Timing Analyst**  
{timing} with slope {signals['slope']:.2f}

**Risk Analyst**  
Volatility at {signals['volatility']:.2f}

**Execution Coach**  
Trade only on confirmation
""")

# =========================================================
# 6. DOWNLOAD
# =========================================================
section("Download PDF")

report = f"""
Signal: {signal_label}
Structure: {structure}
Timing: {timing}
Price: {signals['price']}
"""

st.download_button(
    "Download Report",
    report,
    file_name="report.txt"
)

# =========================================================
# AUTO REFRESH
# =========================================================
time.sleep(2)
st.rerun()
