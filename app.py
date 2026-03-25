import numpy as np
if not hasattr(np, 'bool8'):
    np.bool8 = np.bool_

import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime

try:
    from google import generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# --- 1. SYSTEM CONFIGURATION ---
st.set_page_config(page_title="Crypto Sniper Elite v1.0", layout="wide")

def get_ai_client():
    try:
        if GENAI_AVAILABLE and "GEMINI_API_KEY" in st.secrets:
            return genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        return None
    except Exception:
        return None

client = get_ai_client()

# --- 2. VISUAL STYLING ENGINE ---
def highlight_reco(val):
    if 'STRONG BUY' in str(val):
        color = '#2ecc71'
    elif 'STRONG SELL' in str(val):
        color = '#e74c3c'
    elif 'REVERSION BUY' in str(val):
        color = '#f39c12'
    elif 'ACCUMULATE' in str(val):
        color = '#27ae60'
    else:
        color = '#f1c40f'
    return f'background-color: {color}; color: black; font-weight: bold'

# --- 3. LIVE TOP-500 CRYPTO FETCH (CoinGecko) ---
@st.cache_data(ttl=3600)
def get_top_500_crypto():
    try:
        all_coins = []
        for page in range(1, 6):
            url = (
                f"https://api.coingecko.com/api/v3/coins/markets"
                f"?vs_currency=usd&order=market_cap_desc"
                f"&per_page=100&page={page}&sparkline=false"
            )
            resp = requests.get(url, headers={"Accept": "application/json"}, timeout=15)
            if resp.status_code == 200:
                all_coins.extend(resp.json())
            else:
                break
        if not all_coins:
            raise ValueError("No data from CoinGecko")
        df = pd.DataFrame(all_coins)
        df['yf_ticker'] = df['symbol'].str.upper() + '-USD'
        symbols = df['yf_ticker'].tolist()
        names = dict(zip(df['yf_ticker'], df['name']))
        mcaps = dict(zip(df['yf_ticker'], df['market_cap']))
        sectors = {t: "Crypto" for t in symbols}
        return symbols, sectors, names, mcaps
    except Exception as e:
        st.sidebar.warning(f"CoinGecko failed ({e}). Using fallback list.")
        fallback = [
            "BTC-USD","ETH-USD","BNB-USD","XRP-USD","SOL-USD",
            "ADA-USD","DOGE-USD","AVAX-USD","SHIB-USD","DOT-USD",
            "LINK-USD","MATIC-USD","LTC-USD","BCH-USD","UNI-USD",
            "ATOM-USD","XLM-USD","ETC-USD","HBAR-USD","FIL-USD",
            "APT-USD","ARB-USD","OP-USD","IMX-USD","NEAR-USD",
            "INJ-USD","SUI-USD","TIA-USD","SEI-USD","PYTH-USD",
            "RNDR-USD","FET-USD","AGIX-USD","OCEAN-USD","WLD-USD",
            "GRT-USD","SNX-USD","LDO-USD","RPL-USD","PENDLE-USD",
            "AAVE-USD","CRV-USD","MKR-USD","COMP-USD","YFI-USD",
        ]
        return fallback, {t: "Crypto" for t in fallback}, {t: t.replace("-USD", "") for t in fallback}, {t: 0 for t in fallback}

# --- 4. THE FULL MATH ENGINE ---
def calculate_metrics(df_raw, ticker):
    try:
        if isinstance(df_raw.columns, pd.MultiIndex):
            if ticker in df_raw.columns.get_level_values(1):
                df = df_raw.xs(ticker, axis=1, level=1)
            else:
                return None
        else:
            df = df_raw.copy()
        df.columns = [c.lower() for c in df.columns]
        if 'close' not in df.columns or len(df) < 30:
            return None
        c = df['close'].values.astype(float)
        h = df['high'].values.astype(float)
        l = df['low'].values.astype(float)
        v = df['volume'].values.astype(float)

        def sma(arr, n):
            return pd.Series(arr).rolling(n).mean().values

        m20 = sma(c, 20)[-1]
        m50 = sma(c, 50)[-1] if len(c) >= 50 else np.nan
        m200 = sma(c, 200)[-1] if len(c) >= 200 else np.nan

        # ATR (14)
        tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
        atr = round(pd.Series(tr).rolling(14).mean().iloc[-1], 4)

        # ADX (14)
        plus_dm = np.where((h[1:]-h[:-1]) > (l[:-1]-l[1:]), np.maximum(h[1:]-h[:-1], 0), 0)
        minus_dm = np.where((l[:-1]-l[1:]) > (h[1:]-h[:-1]), np.maximum(l[:-1]-l[1:], 0), 0)
        tr_s = pd.Series(tr).rolling(14).mean()
        plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / tr_s)
        minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / tr_s)
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        adx = dx.rolling(14).mean().iloc[-1]

        # Momentum & Volume
        z = (c[-1] - m20) / (np.std(c[-20:]) + 1e-9)
        vol = v[-1] / (np.mean(v[-20:]) + 1e-9)
        p = (c[-1] - c[-2]) / (c[-2] + 1e-9)
        p7 = (c[-1] - c[-7]) / (c[-7] + 1e-9) if len(c) >= 7 else 0
        p30 = (c[-1] - c[-30]) / (c[-30] + 1e-9) if len(c) >= 30 else 0

        # Miro Score (institutional hot-money detector)
        miro = 2 + (5 if vol > 2.0 else 0) + (3 if p > 0.01 else 0)

        # Final Signal Mapping
        if p > 0.02 and vol > 2.2:
            reco = "STRONG BUY"
        elif p < -0.02 and vol > 2.2:
            reco = "STRONG SELL"
        elif z < -2.2:
            reco = "REVERSION BUY"
        elif not np.isnan(m200) and c[-1] > m200 and adx > 25:
            reco = "ACCUMULATE"
        else:
            reco = "NEUTRAL"

        return {
            "cp": round(c[-1], 6), "m20": round(m20, 4),
            "m50": round(m50, 4) if not np.isnan(m50) else "N/A",
            "m200": round(m200, 4) if not np.isnan(m200) else "N/A",
            "adx": round(adx, 1), "z": round(z, 2), "vol": round(vol, 2),
            "atr": atr, "reco": reco, "miro": miro,
            "p7": round(p7 * 100, 2), "p30": round(p30 * 100, 2),
        }
    except Exception:
        return None

# --- 5. INTERFACE & SIDEBAR ---
st.sidebar.title("Crypto Sniper v1.0")
st.sidebar.subheader(f"📅 {datetime.now().strftime('%b %d, %Y')} Pulse")

try:
    btc_price = round(yf.Ticker("BTC-USD").fast_info.last_price, 2)
    eth_price = round(yf.Ticker("ETH-USD").fast_info.last_price, 2)
except Exception:
    btc_price = eth_price = "N/A"

st.sidebar.table(pd.DataFrame({
    "Metric": ["BTC ($)", "ETH ($)"],
    "Value": [str(btc_price), str(eth_price)]
}))

scan_depth = st.sidebar.slider("Scan Depth", 10, 500, 100)

# --- 6. SCAN EXECUTION ---
if st.sidebar.button("🚀 EXECUTE FULL CRYPTO AUDIT"):
    symbols, sectors, names, mcaps = get_top_500_crypto()
    all_data, errors = [], 0
    prog = st.progress(0, text="Initialising Crypto Scan...")
    scan_syms = symbols[:scan_depth]
    chunks = [scan_syms[i:i + 50] for i in range(0, len(scan_syms), 50)]
    processed = 0
    for chunk in chunks:
        try:
            raw = yf.download(
                chunk, period="1y", interval="1d",
                group_by="ticker", auto_adjust=True,
                progress=False, threads=True
            )
        except Exception:
            processed += len(chunk)
            errors += len(chunk)
            continue
        for t in chunk:
            prog.progress(processed / len(scan_syms), text=f"Scanning {t}... ({processed}/{len(scan_syms)})")
            m = calculate_metrics(raw, t)
            if m:
                all_data.append({
                    "Ticker": t, "Name": names.get(t, t.replace("-USD", "")),
                    "Price": m["cp"], "MA 20": m["m20"], "MA 50": m["m50"],
                    "MA 200": m["m200"], "ADX": m["adx"], "Z-Score": m["z"],
                    "Vol_Surge": m["vol"], "ATR": m["atr"], "7D%": m["p7"],
                    "30D%": m["p30"], "Miro_Score": m["miro"],
                    "Recommendation": m["reco"], "Sector": sectors.get(t, "Crypto"),
                })
            else:
                errors += 1
            processed += 1
    prog.progress(1.0, text=f"✅ Done! {len(all_data)} coins scanned. ({errors} skipped)")
    if all_data:
        st.session_state['crypto_res'] = pd.DataFrame(all_data)

# --- 7. TABS & TACTICAL LOGIC ---
if 'crypto_res' in st.session_state:
    df = st.session_state['crypto_res']
    df_hm = df.copy()
    for col in ["MA 20", "MA 200"]:
        df_hm[col] = pd.to_numeric(df_hm[col], errors='coerce')
    above_200 = len(df_hm[df_hm['MA 200'].notna() & (df_hm['Price'] > df_hm['MA 200'])])
    breadth = (above_200 / len(df)) * 100
    st.sidebar.markdown("---")
    st.sidebar.subheader("Market Heatmap")
    if breadth > 60:
        st.sidebar.success(f"🔥 BULL REGIME ({round(breadth, 1)}%)")
    elif breadth < 40:
        st.sidebar.error(f"🧊 BEAR REGIME ({round(breadth, 1)}%)")
    else:
        st.sidebar.warning(f"⚖️ NEUTRAL REGIME ({round(breadth, 1)}%)")

    v_risk = st.sidebar.number_input("Risk Capital (USD)", value=1000)
    df_hm['Stop_Loss'] = df_hm['Price'] - (2.0 * df_hm['ATR'])
    df_hm['Qty'] = (v_risk / (df_hm['Price'] - df_hm['Stop_Loss'])).replace(
        [np.inf, -np.inf], 0).fillna(0).astype(int)

    t0, t1, t2, t3, t4, t5 = st.tabs([
        "🎯 Miro Flow", "📈 Trend & ADX", "🔄 Reversion",
        "💎 Weekly Sniper", "📂 Filing Audit", "🧠 Intelligence Lab"
    ])

    with t0:
        st.subheader("🎯 Miro Momentum Leaderboard")
        st.caption("Hot-money institutional detection — coins with smart money flowing in NOW")
        mf = df[["Ticker","Name","Price","Recommendation","Miro_Score","Vol_Surge","7D%","30D%"]].sort_values("Miro_Score", ascending=False)
        st.dataframe(mf.style.map(highlight_reco, subset=['Recommendation']), hide_index=True, use_container_width=True)
        with st.expander("📘 TACTICAL LOGIC: Miro Flow"):
            st.markdown("""
**Logic:** Detects Hot Money entering a crypto asset before the crowd.
- **Miro Score (2-10):** High-velocity institutional buying signal.
- **Vol_Surge > 2.0:** Signals mass delivery-based buying.
- **Edge:** Early warning system for breakouts — ideal for swing entries.
""")

    with t1:
        st.subheader("📈 Trend Strength Leaderboard")
        st.caption("ADX > 25 = strong trend. ADX > 40 = explosive trend.")
        tf = df[["Ticker","Name","Price","MA 20","MA 50","MA 200","ADX","Recommendation","Sector"]].sort_values("ADX", ascending=False)
        st.dataframe(tf.style.map(highlight_reco, subset=['Recommendation']), hide_index=True, use_container_width=True)
        with st.expander("📘 TACTICAL LOGIC: Trend & ADX"):
            st.markdown("""
**Logic:** ADX measures trend strength regardless of direction.
- **ADX > 25:** Trending market — ride the wave.
- **ADX < 20:** Ranging — avoid momentum entries.
- **MA Stack (20 > 50 > 200):** Bull alignment — highest conviction buy zone.
""")

    with t2:
        st.subheader("🔄 Mean Reversion Opportunities")
        st.caption("Z-Score < -2.2 = statistically oversold — snap-back candidates")
        rf = df[["Ticker","Name","Price","MA 20","Z-Score","ATR","Recommendation"]].sort_values("Z-Score", ascending=True)
        st.dataframe(rf.style.map(highlight_reco, subset=['Recommendation']), hide_index=True, use_container_width=True)
        with st.expander("📘 TACTICAL LOGIC: Reversion"):
            st.markdown("""
**Logic:** Z-Score measures deviation from the 20-day mean.
- **Z-Score < -2.2:** Rubber Band stretched to the downside.
- **Edge:** High probability snap-back to MA 20 within 1-3 sessions.
""")

    with t3:
        st.subheader("💎 Weekly Institutional Flow")
        st.caption("Tracking where Whales and Funds are Building a Wall")
        wf = df[["Ticker","Name","Price","Recommendation","Vol_Surge","7D%","30D%","Sector"]].sort_values("Vol_Surge", ascending=False)
        st.dataframe(wf.style.map(highlight_reco, subset=['Recommendation']), hide_index=True, use_container_width=True)
        with st.expander("📘 TACTICAL LOGIC: Weekly Sniper"):
            st.markdown("""
**Logic:** Tracks where Whales and On-Chain funds are Building a Wall.
- **Vol_Surge > 2.0:** Institution absorbing all available sellers.
- **Edge:** Small price move + massive volume = violent breakout incoming.
""")

    with t4:
        st.subheader("📂 Crypto Intelligence Audit")
        t_f = st.selectbox("Select Asset for Audit", df['Ticker'].tolist(), key="audit_select")
        cn = df[df['Ticker'] == t_f]['Name'].values[0] if len(df[df['Ticker'] == t_f]) else t_f
        cd = df[df['Ticker'] == t_f].to_dict('records')
        cd = cd[0] if cd else {}
        if st.button("🔍 Run AI Audit"):
            if client:
                prompt = (
                    f"Today is {datetime.now().strftime('%B %d, %Y')}. "
                    f"You are a senior crypto analyst. Comprehensive audit for {cn} ({t_f}). "
                    f"Data: {cd}. Cover: 1) On-chain fundamentals 2) Macro environment "
                    f"3) Technical structure 4) Upcoming catalysts and risks "
                    f"5) Institutional interest signals. Clear sections + final verdict."
                )
                with st.spinner("Analysing..."):
                    try:
                        st.markdown(client.models.generate_content(model="gemini-2.5-flash", contents=prompt).text)
                    except Exception as e:
                        st.error(f"AI Error: {e}")
            else:
                st.info("Add GEMINI_API_KEY to Streamlit secrets to enable AI features.")
                st.markdown(f"### {cn} ({t_f}) — Scanner Data")
                [st.write(f"**{k}:** {v}") for k, v in cd.items()]

    with t5:
        st.subheader("🧠 Crypto Council Debate")
        t_i = st.selectbox("Select Asset for Debate", df['Ticker'].tolist(), key="debate_select")
        cn_i = df[df['Ticker'] == t_i]['Name'].values[0] if len(df[df['Ticker'] == t_i]) else t_i
        cd_i = df[df['Ticker'] == t_i].to_dict('records')
        cd_i = cd_i[0] if cd_i else {}
        if st.button("🤖 Summon Council"):
            if client:
                prompt = (
                    f"Today is {datetime.now().strftime('%B %d, %Y')}. "
                    f"Simulate a 4-agent debate for {cn_i} ({t_i}). "
                    f"Context: BTC={btc_price}, ETH={eth_price}. Data: {cd_i}. "
                    f"Agents: BULL WHALE, BEAR TRADER, QUANT ANALYST, RISK MANAGER. "
                    f"Each agent gives their view, then FINAL CONSENSUS. Sharp, data-driven, actionable."
                )
                with st.spinner("Debating..."):
                    try:
                        st.markdown(client.models.generate_content(model="gemini-2.5-flash", contents=prompt).text)
                    except Exception as e:
                        st.error(f"AI Error: {e}")
            else:
                st.info("Add GEMINI_API_KEY to Streamlit secrets to enable AI features.")
                st.markdown(f"### {cn_i} ({t_i}) — Scanner Snapshot")
                cols = st.columns(3)
                [cols[i % 3].metric(k, v) for i, (k, v) in enumerate(cd_i.items())]

else:
    st.info("Scanner Ready. Click 'EXECUTE FULL CRYPTO AUDIT' to begin.")
    st.markdown("""
---
### 🪙 Crypto Sniper Elite v1.0
Nifty Sniper v16.0 logic rebuilt for the top 500 crypto markets.

| Signal | What it means |
|--------|---------------|
| STRONG BUY | Price surge + 2x volume — smart money entering NOW |
| STRONG SELL | Panic dump + volume — distribution phase |
| REVERSION BUY | Statistically oversold (Z < -2.2) — snap-back imminent |
| ACCUMULATE | Above MA200 + ADX > 25 — trend confirmed |
| NEUTRAL | No clear directional bias — stand aside |

**Powered by:** CoinGecko (universe) + yfinance (OHLCV) + Gemini AI (audit)
""")
