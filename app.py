import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import time
import random
from datetime import datetime

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

st.set_page_config(page_title="Crypto Sniper Elite v1.0", layout="wide")

# ── AI CLIENT ──────────────────────────────────────────
def get_ai_client():
    try:
        if GENAI_AVAILABLE and "GEMINI_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            return genai.GenerativeModel("gemini-1.5-flash")
        return None
    except Exception:
        return None

client = get_ai_client()

# ── COLOUR CODING ──────────────────────────────────────
def highlight_reco(val):
    c = {"STRONG BUY":"#2ecc71","STRONG SELL":"#e74c3c",
         "REVERSION BUY":"#f39c12","ACCUMULATE":"#27ae60","NEUTRAL":"#f1c40f"}
    for k,v in c.items():
        if k in str(val):
            return f"background-color:{v};color:black;font-weight:bold"
    return ""

# ── TOP-500 UNIVERSE ───────────────────────────────────
@st.cache_data(ttl=3600)
def get_universe():
    try:
        coins = []
        for page in range(1, 6):
            r = requests.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={"vs_currency":"usd","order":"market_cap_desc",
                        "per_page":100,"page":page,"sparkline":"false"},
                headers={"Accept":"application/json",
                         "User-Agent":"Mozilla/5.0"},
                timeout=20)
            if r.status_code == 200:
                data = r.json()
                if data:
                    coins.extend(data)
                time.sleep(1.5)
            else:
                break
        if not coins:
            raise ValueError("Empty")
        df = pd.DataFrame(coins)
        df["ticker"] = df["symbol"].str.upper() + "-USD"
        return (df["ticker"].tolist(),
                {row["ticker"]: row["name"] for _, row in df.iterrows()})
    except Exception as e:
        # Hardcoded top-50 fallback — always works
        fb = [
            "BTC-USD","ETH-USD","BNB-USD","XRP-USD","SOL-USD",
            "ADA-USD","DOGE-USD","AVAX-USD","DOT-USD","LINK-USD",
            "LTC-USD","BCH-USD","UNI3-USD","ATOM-USD","XLM-USD",
            "ETC-USD","NEAR-USD","AAVE-USD","MKR-USD","COMP-USD",
            "GRT-USD","FIL-USD","HBAR-USD","APT21794-USD","ARB11841-USD",
            "OP-USD","IMX10603-USD","RNDR-USD","FET-USD","WLD-USD",
        ]
        names = {t: t.replace("-USD","") for t in fb}
        return fb, names

# ── OHLCV via Ticker.history() — most stable yfinance method ──
def fetch_ohlcv(ticker: str):
    for attempt in range(3):
        try:
            time.sleep(random.uniform(0.3, 0.8))
            t = yf.Ticker(ticker)
            df = t.history(period="1y", interval="1d", auto_adjust=True,
                           raise_errors=False)
            if df is None or len(df) < 30:
                return None
            df.columns = [c.lower() for c in df.columns]
            if "close" not in df.columns:
                return None
            df = df.dropna(subset=["close","high","low","volume"])
            return df if len(df) >= 30 else None
        except Exception:
            time.sleep(2 ** attempt)
    return None

# ── MATH ENGINE ────────────────────────────────────────
def calc(df):
    try:
        c = df["close"].values.astype(float)
        h = df["high"].values.astype(float)
        l = df["low"].values.astype(float)
        v = df["volume"].values.astype(float)
        n = min(len(c),len(h),len(l),len(v))
        c,h,l,v = c[-n:],h[-n:],l[-n:],v[-n:]
        if n < 30:
            return None

        def sma(a, w):
            return float(pd.Series(a).rolling(w).mean().iloc[-1])

        m20  = sma(c, 20)
        m50  = sma(c, 50)  if n >= 50  else float("nan")
        m200 = sma(c, 200) if n >= 200 else float("nan")

        tr   = np.maximum(h[1:]-l[1:],
               np.maximum(np.abs(h[1:]-c[:-1]), np.abs(l[1:]-c[:-1])))
        atr  = round(float(pd.Series(tr).rolling(14).mean().iloc[-1]), 6)

        pdm  = np.where((h[1:]-h[:-1])>(l[:-1]-l[1:]),np.maximum(h[1:]-h[:-1],0),0)
        mdm  = np.where((l[:-1]-l[1:])>(h[1:]-h[:-1]),np.maximum(l[:-1]-l[1:],0),0)
        trs  = pd.Series(tr).rolling(14).mean()
        pdi  = 100*(pd.Series(pdm).rolling(14).mean()/(trs+1e-9))
        mdi  = 100*(pd.Series(mdm).rolling(14).mean()/(trs+1e-9))
        dx   = (np.abs(pdi-mdi)/(pdi+mdi+1e-9))*100
        adx  = float(dx.rolling(14).mean().iloc[-1])

        z    = float((c[-1]-m20)/(np.std(c[-20:])+1e-9))
        vs   = float(v[-1]/(np.mean(v[-20:])+1e-9))
        p1   = float((c[-1]-c[-2])/(c[-2]+1e-9))
        p7   = float((c[-1]-c[-7])/(c[-7]+1e-9))  if n>=7  else 0.0
        p30  = float((c[-1]-c[-30])/(c[-30]+1e-9)) if n>=30 else 0.0
        miro = 2+(5 if vs>2.0 else 0)+(3 if p1>0.01 else 0)

        if   p1> 0.02 and vs>2.2: sig="STRONG BUY"
        elif p1<-0.02 and vs>2.2: sig="STRONG SELL"
        elif z <-2.2:              sig="REVERSION BUY"
        elif not np.isnan(m200) and c[-1]>m200 and adx>25: sig="ACCUMULATE"
        else:                      sig="NEUTRAL"

        return dict(
            Price  = round(float(c[-1]),6),
            MA20   = round(m20,4),
            MA50   = round(m50,4)  if not np.isnan(m50)  else "N/A",
            MA200  = round(m200,4) if not np.isnan(m200) else "N/A",
            ADX    = round(adx,1),
            ZScore = round(z,2),
            VolSrg = round(vs,2),
            ATR    = atr,
            Chg7D  = round(p7*100,2),
            Chg30D = round(p30*100,2),
            Miro   = miro,
            Signal = sig,
        )
    except Exception:
        return None

# ── SIDEBAR ────────────────────────────────────────────
st.sidebar.title("Crypto Sniper v1.0")
st.sidebar.subheader(f"📅 {datetime.now().strftime('%b %d, %Y')} Pulse")

@st.cache_data(ttl=300)
def live_prices():
    try:
        b = yf.Ticker("BTC-USD").history(period="2d")["Close"]
        e = yf.Ticker("ETH-USD").history(period="2d")["Close"]
        return round(float(b.iloc[-1]),2), round(float(e.iloc[-1]),2)
    except Exception:
        return "N/A","N/A"

btc_p, eth_p = live_prices()
st.sidebar.table(pd.DataFrame({
    "Metric":["BTC ($)","ETH ($)"],
    "Value":[str(btc_p),str(eth_p)]}))

scan_n = st.sidebar.slider("Scan Depth", 10, 100, 20)
st.sidebar.caption("⚠️ Each coin ~1s. 20 coins ≈ 30s. 100 coins ≈ 3min.")

# ── SCAN ───────────────────────────────────────────────
if st.sidebar.button("🚀 EXECUTE FULL CRYPTO AUDIT"):
    tickers, names = get_universe()
    scan_list = tickers[:scan_n]
    rows, skipped = [], 0
    bar  = st.progress(0.0, text="Fetching universe…")
    stat = st.empty()

    for i, t in enumerate(scan_list):
        pct = (i+1)/len(scan_list)
        bar.progress(pct, text=f"⏳ {t}  ({i+1}/{len(scan_list)}) — {len(rows)} signals so far")
        df = fetch_ohlcv(t)
        if df is not None:
            m = calc(df)
            if m:
                rows.append({"Ticker":t,"Name":names.get(t,t),**m})
                stat.success(f"✅ {t}  →  {m['Signal']}  |  Price: {m['Price']}")
            else:
                skipped += 1
                stat.warning(f"⚠️ {t} — insufficient data")
        else:
            skipped += 1
            stat.warning(f"⚠️ {t} — download failed, skipping")

    bar.progress(1.0, text=f"✅ Complete — {len(rows)} coins analysed | {skipped} skipped")
    if rows:
        st.session_state["res"]  = pd.DataFrame(rows)
        st.session_state["btc"]  = btc_p
        st.session_state["eth"]  = eth_p
        st.session_state["names"]= names
        st.rerun()
    else:
        st.error("No results — Yahoo Finance may be rate-limiting. Wait 60s and retry.")

# ── RESULTS ────────────────────────────────────────────
if "res" in st.session_state:
    df   = st.session_state["res"]
    bpx  = st.session_state.get("btc","N/A")
    epx  = st.session_state.get("eth","N/A")
    nms  = st.session_state.get("names",{})

    df_n = df.copy()
    df_n["MA200n"] = pd.to_numeric(df_n["MA200"], errors="coerce")
    above = (df_n["MA200n"].notna() & (df_n["Price"]>df_n["MA200n"])).sum()
    brd   = above/len(df)*100
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Market Heatmap")
    if   brd>60: st.sidebar.success(f"🔥 BULL REGIME  {round(brd,1)}%")
    elif brd<40: st.sidebar.error(  f"🧊 BEAR REGIME  {round(brd,1)}%")
    else:        st.sidebar.warning(f"⚖️ NEUTRAL      {round(brd,1)}%")

    risk = st.sidebar.number_input("Risk Capital ($)", value=1000, step=100)
    df["StopLoss"] = df["Price"] - 2.0*df["ATR"]
    df["Qty"] = (risk/(df["Price"]-df["StopLoss"])
                 ).replace([np.inf,-np.inf],0).fillna(0).round(0).astype(int)

    T = st.tabs(["🎯 Miro Flow","📈 Trend & ADX","🔄 Reversion",
                 "💎 Weekly Sniper","📂 AI Audit","🧠 Council Debate"])

    def tbl(frame, cols):
        st.dataframe(
            frame[cols].style.map(highlight_reco, subset=["Signal"]),
            hide_index=True, use_container_width=True)

    with T[0]:
        st.subheader("🎯 Miro Momentum Leaderboard")
        st.caption("Hot-money detection — coins with institutional flow NOW")
        tbl(df.sort_values("Miro",ascending=False),
            ["Ticker","Name","Price","Signal","Miro","VolSrg","Chg7D","Chg30D"])
        with st.expander("📘 Tactical Logic"):
            st.markdown("**Miro 2-10:** hot-money velocity. "
                        "**VolSrg>2:** institutional accumulation. "
                        "**Edge:** early breakout warning for swing entries.")

    with T[1]:
        st.subheader("📈 Trend Strength Leaderboard")
        st.caption("ADX>25 = trending | ADX>40 = explosive")
        tbl(df.sort_values("ADX",ascending=False),
            ["Ticker","Name","Price","MA20","MA50","MA200","ADX","Signal"])
        with st.expander("📘 Tactical Logic"):
            st.markdown("**ADX>25:** ride the wave. "
                        "**MA Stack 20>50>200:** highest-conviction bull zone.")

    with T[2]:
        st.subheader("🔄 Mean Reversion — Snap-Back Candidates")
        st.caption("Z-Score < -2.2 = statistically oversold")
        tbl(df.sort_values("ZScore",ascending=True),
            ["Ticker","Name","Price","MA20","ZScore","ATR","Signal"])
        with st.expander("📘 Tactical Logic"):
            st.markdown("**Z<-2.2:** rubber band stretched. "
                        "High prob snap-back to MA20 in 1-3 sessions.")

    with T[3]:
        st.subheader("💎 Weekly Institutional Flow")
        st.caption("Where whales are building walls")
        tbl(df.sort_values("VolSrg",ascending=False),
            ["Ticker","Name","Price","Signal","VolSrg","Chg7D","Chg30D"])
        with st.expander("📘 Tactical Logic"):
            st.markdown("**VolSrg>2:** institution absorbing sellers. "
                        "Small price + massive vol = violent breakout incoming.")

    with T[4]:
        st.subheader("📂 AI Audit")
        pick = st.selectbox("Select asset", df["Ticker"].tolist(), key="a_pick")
        row  = df[df["Ticker"]==pick].to_dict("records")
        row  = row[0] if row else {}
        if st.button("🔍 Run AI Audit", key="btn_audit"):
            if client:
                p = (f"Today is {datetime.now().strftime('%B %d, %Y')}. "
                     f"You are a senior crypto analyst. "
                     f"Comprehensive audit for {nms.get(pick,pick)} ({pick}). "
                     f"Live scanner data: {row}. BTC={bpx}, ETH={epx}. "
                     f"Cover: 1)On-chain 2)Macro 3)Technicals "
                     f"4)Catalysts/risks 5)Institutional signals. "
                     f"Conclude with a clear BUY/HOLD/SELL verdict.")
                with st.spinner("Analysing…"):
                    try:
                        st.markdown(client.generate_content(p).text)
                    except Exception as ex:
                        st.error(f"AI error: {ex}")
            else:
                st.info("Add GEMINI_API_KEY to Streamlit secrets to enable AI.")
                st.json(row)

    with T[5]:
        st.subheader("🧠 Council Debate")
        pick2 = st.selectbox("Select asset", df["Ticker"].tolist(), key="d_pick")
        row2  = df[df["Ticker"]==pick2].to_dict("records")
        row2  = row2[0] if row2 else {}
        if st.button("🤖 Summon Council", key="btn_debate"):
            if client:
                p2 = (f"Today is {datetime.now().strftime('%B %d, %Y')}. "
                      f"Run a 4-agent debate on {nms.get(pick2,pick2)} ({pick2}). "
                      f"Scanner data: {row2}. BTC={bpx}, ETH={epx}. "
                      f"Agents: BULL WHALE | BEAR TRADER | QUANT | RISK MGR. "
                      f"Each gives their sharpest view, then FINAL CONSENSUS verdict.")
                with st.spinner("Debating…"):
                    try:
                        st.markdown(client.generate_content(p2).text)
                    except Exception as ex:
                        st.error(f"AI error: {ex}")
            else:
                st.info("Add GEMINI_API_KEY to Streamlit secrets to enable AI.")
                cols = st.columns(3)
                [cols[i%3].metric(k,v) for i,(k,v) in enumerate(row2.items())]

else:
    st.info("Scanner Ready. Set scan depth and click **EXECUTE FULL CRYPTO AUDIT**.")
    st.markdown("""---
### 🪙 Crypto Sniper Elite v1.0
Nifty Sniper v16.0 logic — rebuilt for the top 500 crypto markets.

| Signal | Meaning |
|--------|---------|
| 🚀 STRONG BUY | Price+2 surge + 2× volume — institutional entry NOW |
| 🔴 STRONG SELL | Dump + volume — distribution phase |
| 🔄 REVERSION BUY | Z-Score < −2.2 — snap-back imminent |
| ✅ ACCUMULATE | Above MA200 + ADX>25 — confirmed uptrend |
| 🟡 NEUTRAL | No clear edge — stand aside |

**Data:** CoinGecko (universe) · yfinance Ticker.history() · Gemini AI
""")
