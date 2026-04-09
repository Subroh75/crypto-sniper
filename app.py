# ╔══════════════════════════════════════════════════════════════════╗
# ║  CRYPTO GURU — Intelligence Terminal v2.0                       ║
# ║  Search any coin → Project overview · News · TA · AI Council   ║
# ║  Data: CryptoCompare  ·  AI: Gemini  ·  Domain: crypto.guru    ║
# ╚══════════════════════════════════════════════════════════════════╝

import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timedelta

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Crypto Guru · Intelligence Terminal",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS — dark terminal, no sidebar ──────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap');
*, *::before, *::after { box-sizing: border-box; }
html, body, .stApp { background: #0a0a0f !important; color: #e2e8f0; font-family: 'Inter', sans-serif; }
section[data-testid="stSidebar"] { display: none !important; }
.block-container { max-width: 900px; margin: 0 auto; padding: 2rem 1.5rem; }

/* hero */
.hero {
    background: linear-gradient(135deg, #0d0d14 0%, #0a1020 100%);
    border: 1px solid #1e2030;
    border-radius: 16px;
    padding: 40px 32px 32px;
    text-align: center;
    margin-bottom: 32px;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: '';
    position: absolute;
    top: -80px; left: 50%; transform: translateX(-50%);
    width: 500px; height: 260px;
    background: radial-gradient(ellipse, #ff660018 0%, transparent 70%);
    pointer-events: none;
}
.hero-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 2.4rem; font-weight: 700;
    background: linear-gradient(135deg, #ff6600, #ff9d00);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
}
.hero-sub { font-size: 1rem; color: #64748b; margin-bottom: 28px; }

/* search */
.stTextInput > div > div > input {
    background: #0d1117 !important;
    border: 1px solid #2a2d3e !important;
    border-radius: 12px !important;
    color: #e2e8f0 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 1.1rem !important;
    padding: 14px 20px !important;
    text-align: center;
    transition: border-color .2s;
}
.stTextInput > div > div > input:focus {
    border-color: #ff6600 !important;
    box-shadow: 0 0 0 3px #ff660020 !important;
}
.stTextInput > div > div > input::placeholder { color: #475569 !important; }
.stTextInput label { display: none !important; }

/* buttons */
.stButton > button {
    background: linear-gradient(135deg, #ff6600, #ff8c00) !important;
    color: #fff !important; border: none !important;
    border-radius: 10px !important; font-weight: 600 !important;
    padding: 10px 28px !important;
    transition: opacity .15s;
}
.stButton > button:hover { opacity: .88 !important; }

/* section cards */
.section-card {
    background: #0d1117;
    border: 1px solid #1e2030;
    border-radius: 14px;
    padding: 24px 28px;
    margin-bottom: 20px;
}
.section-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: .75rem; font-weight: 700;
    letter-spacing: .12em; text-transform: uppercase;
    color: #ff6600; margin-bottom: 16px;
}

/* coin hero card */
.coin-hero {
    display: flex; align-items: center; gap: 20px;
    margin-bottom: 20px;
}
.coin-logo { width: 64px; height: 64px; border-radius: 50%; }
.coin-name { font-size: 1.8rem; font-weight: 700; color: #e2e8f0; }
.coin-symbol { font-family: 'JetBrains Mono', monospace; font-size: 1rem; color: #64748b; }
.coin-price { font-family: 'JetBrains Mono', monospace; font-size: 2rem; font-weight: 700; color: #e2e8f0; }
.chg-pos { color: #22c55e; } .chg-neg { color: #ef4444; }

/* metric grid */
.metric-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 12px; }
.metric-box { background: #131620; border: 1px solid #1e2030; border-radius: 10px; padding: 14px 16px; }
.metric-label { font-size: .7rem; color: #64748b; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 4px; }
.metric-val { font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; font-weight: 600; color: #e2e8f0; }

/* news */
.news-item {
    border-left: 3px solid #ff6600;
    padding: 12px 16px;
    margin-bottom: 12px;
    background: #131620;
    border-radius: 0 8px 8px 0;
}
.news-title { font-size: .95rem; font-weight: 500; color: #e2e8f0; margin-bottom: 4px; }
.news-meta { font-size: .75rem; color: #475569; }
.sentiment-pos { color: #22c55e; } .sentiment-neg { color: #ef4444; } .sentiment-neu { color: #94a3b8; }

/* signal chip */
.signal-chip {
    display: inline-block; padding: 6px 16px;
    border-radius: 20px; font-family: 'JetBrains Mono', monospace;
    font-size: .8rem; font-weight: 700; letter-spacing: .08em;
}
.chip-buy { background: #14532d; color: #4ade80; border: 1px solid #166534; }
.chip-sell { background: #450a0a; color: #f87171; border: 1px solid #7f1d1d; }
.chip-hold { background: #1c1917; color: #fbbf24; border: 1px solid #44403c; }
.chip-acc { background: #0c1a2e; color: #60a5fa; border: 1px solid #1e3a5f; }

/* TA bars */
.ta-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.ta-label { font-size: .8rem; color: #94a3b8; width: 120px; flex-shrink: 0; }
.ta-bar-bg { flex: 1; height: 6px; background: #1e2030; border-radius: 3px; }
.ta-bar-fill { height: 100%; border-radius: 3px; }
.ta-val { font-family: 'JetBrains Mono', monospace; font-size: .8rem; color: #e2e8f0; width: 60px; text-align: right; }

/* agent debate */
.agent-block { border: 1px solid #1e2030; border-radius: 12px; padding: 18px 20px; margin-bottom: 12px; }
.agent-name { font-size: .75rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; margin-bottom: 8px; }
.agent-text { font-size: .9rem; color: #94a3b8; line-height: 1.6; }
.verdict-banner {
    background: linear-gradient(135deg, #0f1f10, #0a1f0a);
    border: 1px solid #166534; border-radius: 12px;
    padding: 20px 24px; text-align: center; margin-top: 16px;
}
.verdict-label { font-size: .7rem; color: #4ade80; text-transform: uppercase; letter-spacing: .12em; margin-bottom: 8px; }
.verdict-text { font-size: 1.1rem; font-weight: 600; color: #e2e8f0; }

/* loader */
.stSpinner > div { border-top-color: #ff6600 !important; }

hr { border-color: #1e2030 !important; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
CC_BASE = "https://min-api.cryptocompare.com/data"
CC_KEY  = st.secrets.get("CRYPTOCOMPARE_API_KEY", "")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "")

def cc_headers():
    h = {"Content-Type": "application/json"}
    if CC_KEY:
        h["authorization"] = f"Apikey {CC_KEY}"
    return h

# ── Data helpers ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=120)
def get_coin_price(symbol: str) -> dict:
    try:
        url = f"{CC_BASE}/pricemultifull?fsyms={symbol}&tsyms=USD"
        r = requests.get(url, headers=cc_headers(), timeout=8)
        raw = r.json().get("RAW", {}).get(symbol, {}).get("USD", {})
        return {
            "price":      raw.get("PRICE", 0),
            "chg24":      raw.get("CHANGEPCT24HOUR", 0),
            "chg7d":      raw.get("CHANGE7DAYSPCT", 0),
            "high24":     raw.get("HIGH24HOUR", 0),
            "low24":      raw.get("LOW24HOUR", 0),
            "vol24":      raw.get("VOLUME24HOURTO", 0),
            "mktcap":     raw.get("MKTCAP", 0),
            "supply":     raw.get("SUPPLY", 0),
            "imgurl":     "https://www.cryptocompare.com" + raw.get("IMAGEURL", ""),
            "fullname":   raw.get("FROMSYMBOL", symbol),
        }
    except Exception:
        return {}

@st.cache_data(ttl=300)
def get_coin_info(symbol: str) -> dict:
    try:
        url = f"https://min-api.cryptocompare.com/data/coin/generalinfo?fsym={symbol}&tsym=USD"
        r = requests.get(url, headers=cc_headers(), timeout=8)
        data = r.json().get("Data", {})
        ci = data.get("CoinInfo", {})
        return {
            "name":        ci.get("FullName", symbol),
            "algorithm":   ci.get("Algorithm", "N/A"),
            "proof_type":  ci.get("ProofType", "N/A"),
            "launch_date": ci.get("AssetLaunchDate", "N/A"),
            "description": ci.get("Description", "No description available."),
            "website":     ci.get("Website", ""),
            "whitepaper":  ci.get("TechnicalDoc", ""),
            "twitter":     ci.get("Twitter", ""),
            "reddit":      ci.get("Reddit", ""),
            "github":      ci.get("Github", ""),
        }
    except Exception:
        return {}

@st.cache_data(ttl=300)
def get_ohlcv(symbol: str, limit: int = 100) -> pd.DataFrame:
    try:
        url = f"{CC_BASE}/v2/histoday?fsym={symbol}&tsym=USD&limit={limit}"
        r = requests.get(url, headers=cc_headers(), timeout=10)
        data = r.json().get("Data", {}).get("Data", [])
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.set_index("time")
        return df[["open", "high", "low", "close", "volumeto"]].rename(
            columns={"volumeto": "volume"})
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=180)
def get_news(symbol: str) -> list:
    try:
        url = f"{CC_BASE}/v2/news/?categories={symbol}&lang=EN&sortOrder=latest"
        r = requests.get(url, headers=cc_headers(), timeout=8)
        return r.json().get("Data", [])[:8]
    except Exception:
        return []

# ── Technical Analysis ────────────────────────────────────────────────────────
def compute_ta(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 20:
        return {}
    c = df["close"]
    v = df["volume"]

    def ema(s, n): return s.ewm(span=n, adjust=False).mean()
    def sma(s, n): return s.rolling(n).mean()

    ma20  = sma(c, 20).iloc[-1]
    ma50  = sma(c, 50).iloc[-1] if len(c) >= 50 else None
    ma200 = sma(c, 200).iloc[-1] if len(c) >= 200 else None
    price = c.iloc[-1]

    # RSI
    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs   = gain / loss.replace(0, np.nan)
    rsi  = float((100 - 100 / (1 + rs)).iloc[-1])

    # MACD
    macd_line   = ema(c, 12) - ema(c, 26)
    signal_line = ema(macd_line, 9)
    macd_val    = float(macd_line.iloc[-1])
    macd_sig    = float(signal_line.iloc[-1])

    # Bollinger
    bb_mid = sma(c, 20)
    bb_std = c.rolling(20).std()
    bb_up  = float((bb_mid + 2 * bb_std).iloc[-1])
    bb_lo  = float((bb_mid - 2 * bb_std).iloc[-1])

    # ATR
    hl = df["high"] - df["low"]
    hc = (df["high"] - c.shift()).abs()
    lc = (df["low"]  - c.shift()).abs()
    atr = float(pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean().iloc[-1])

    # ADX
    plus_dm  = (df["high"].diff().clip(lower=0))
    minus_dm = (-df["low"].diff().clip(upper=0))
    tr14     = hl.rolling(14).sum()
    adx_raw  = abs(plus_dm.rolling(14).sum() - minus_dm.rolling(14).sum()) / tr14.replace(0, np.nan) * 100
    adx      = float(adx_raw.rolling(14).mean().iloc[-1]) if not adx_raw.empty else 0

    # Vol surge
    avg_vol  = float(v.rolling(20).mean().iloc[-1])
    last_vol = float(v.iloc[-1])
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1

    # Z-score
    zscore = float((price - float(sma(c, 20).iloc[-1])) / float(c.rolling(20).std().iloc[-1]))

    # Signal
    score = 0
    if price > ma20: score += 1
    if ma50 and price > ma50: score += 1
    if ma200 and price > ma200: score += 1
    if rsi < 30: score += 2
    elif rsi > 70: score -= 2
    if macd_val > macd_sig: score += 1
    if vol_ratio > 1.5: score += 1
    if zscore < -1.5: score += 1
    elif zscore > 1.5: score -= 1

    if score >= 5:   signal = "STRONG BUY"
    elif score >= 3: signal = "ACCUMULATE"
    elif score <= -3: signal = "STRONG SELL"
    elif score <= -1: signal = "CAUTION"
    else:            signal = "NEUTRAL"

    return {
        "price": price, "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "rsi": rsi, "macd": macd_val, "macd_sig": macd_sig,
        "bb_up": bb_up, "bb_lo": bb_lo, "atr": atr, "adx": adx,
        "vol_ratio": vol_ratio, "zscore": zscore,
        "signal": signal, "score": score,
    }

# ── Format helpers ────────────────────────────────────────────────────────────
def fmt_price(n):
    if n >= 1000: return f"${n:,.2f}"
    if n >= 1:    return f"${n:.4f}"
    return f"${n:.8f}"

def fmt_large(n):
    if n >= 1e12: return f"${n/1e12:.2f}T"
    if n >= 1e9:  return f"${n/1e9:.2f}B"
    if n >= 1e6:  return f"${n/1e6:.2f}M"
    return f"${n:,.0f}"

def chg_html(v):
    cls = "chg-pos" if v >= 0 else "chg-neg"
    sign = "+" if v >= 0 else ""
    return f'<span class="{cls}">{sign}{v:.2f}%</span>'

def signal_chip(s):
    m = {
        "STRONG BUY": "chip-buy",
        "ACCUMULATE": "chip-acc",
        "NEUTRAL":    "chip-hold",
        "CAUTION":    "chip-hold",
        "STRONG SELL":"chip-sell",
    }
    css = m.get(s, "chip-hold")
    return f'<span class="signal-chip {css}">{s}</span>'

# ── Gemini AI ─────────────────────────────────────────────────────────────────
def run_gemini(prompt: str) -> str:
    if not GENAI_AVAILABLE or not GEMINI_KEY:
        return "_Gemini API key not configured. Add GEMINI_API_KEY to Streamlit secrets._"
    try:
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp  = model.generate_content(prompt)
        return resp.text
    except Exception as e:
        return f"_AI unavailable: {e}_"

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <div class="hero-title">🔮 CRYPTO GURU</div>
  <div class="hero-sub">Intelligence Terminal · Enter any crypto asset to begin</div>
</div>
""", unsafe_allow_html=True)

# ── Search ────────────────────────────────────────────────────────────────────
col_s, col_b = st.columns([5, 1])
with col_s:
    query = st.text_input("", placeholder="Enter ticker or name (e.g. BTC, ETH, SOL, DOGE...)", key="search")
with col_b:
    go = st.button("Analyse", use_container_width=True)

symbol = query.strip().upper() if query else ""

if not symbol:
    st.markdown("""
<div style="text-align:center;margin-top:48px;color:#2a2d3e;">
  <div style="font-size:3rem;">🔮</div>
  <div style="font-family:'JetBrains Mono',monospace;font-size:.85rem;color:#475569;margin-top:12px;">
    Enter a crypto ticker above to get started
  </div>
</div>
""", unsafe_allow_html=True)
    st.stop()

# ── Fetch ─────────────────────────────────────────────────────────────────────
with st.spinner(f"Fetching intelligence for {symbol}…"):
    price_data = get_coin_price(symbol)
    coin_info  = get_coin_info(symbol)
    df_ohlcv   = get_ohlcv(symbol)
    news_items = get_news(symbol)
    ta         = compute_ta(df_ohlcv)

if not price_data or price_data.get("price", 0) == 0:
    st.error(f"⚠️ Could not find data for **{symbol}**. Check the ticker and try again.")
    st.stop()

price  = price_data["price"]
chg24  = price_data["chg24"]
chg7d  = price_data["chg7d"]
imgurl = price_data["imgurl"]
name   = coin_info.get("name") or price_data.get("fullname") or symbol

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — PROJECT OVERVIEW
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.markdown('<div class="section-title">01 · Project Overview</div>', unsafe_allow_html=True)

coin_hero_html = f"""
<div class="coin-hero">
  <img class="coin-logo" src="{imgurl}" onerror="this.style.display='none'" />
  <div>
    <div class="coin-name">{name}</div>
    <div class="coin-symbol">{symbol} · {coin_info.get('algorithm','N/A')} · {coin_info.get('proof_type','N/A')}</div>
  </div>
  <div style="margin-left:auto;text-align:right;">
    <div class="coin-price">{fmt_price(price)}</div>
    <div>{chg_html(chg24)} 24h &nbsp; {chg_html(chg7d)} 7d</div>
  </div>
</div>
<div class="metric-grid">
  <div class="metric-box"><div class="metric-label">Market Cap</div><div class="metric-val">{fmt_large(price_data['mktcap'])}</div></div>
  <div class="metric-box"><div class="metric-label">24h Volume</div><div class="metric-val">{fmt_large(price_data['vol24'])}</div></div>
  <div class="metric-box"><div class="metric-label">Circulating Supply</div><div class="metric-val">{fmt_large(price_data['supply'])}</div></div>
  <div class="metric-box"><div class="metric-label">24h High</div><div class="metric-val">{fmt_price(price_data['high24'])}</div></div>
  <div class="metric-box"><div class="metric-label">24h Low</div><div class="metric-val">{fmt_price(price_data['low24'])}</div></div>
  <div class="metric-box"><div class="metric-label">Launch Date</div><div class="metric-val">{coin_info.get('launch_date','N/A')}</div></div>
</div>
"""
st.markdown(coin_hero_html, unsafe_allow_html=True)

desc = coin_info.get("description", "")
if desc:
    st.markdown(f"<p style='margin-top:16px;font-size:.9rem;color:#94a3b8;line-height:1.7'>{desc[:800]}{'...' if len(desc)>800 else ''}</p>", unsafe_allow_html=True)

links = []
if coin_info.get("website"):   links.append(f"[🌐 Website]({coin_info['website']})")
if coin_info.get("whitepaper"):links.append(f"[📄 Whitepaper]({coin_info['whitepaper']})")
if coin_info.get("twitter"):   links.append(f"[🐦 Twitter]({coin_info['twitter']})")
if coin_info.get("reddit"):    links.append(f"[🔴 Reddit]({coin_info['reddit']})")
if links:
    st.markdown("  ·  ".join(links))

st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — NEWS & SENTIMENT
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.markdown('<div class="section-title">02 · News & Market Sentiment</div>', unsafe_allow_html=True)

if news_items:
    for item in news_items:
        title = item.get("title", "")
        source = item.get("source_info", {}).get("name", item.get("source", ""))
        ts = datetime.fromtimestamp(item.get("published_on", 0)).strftime("%b %d, %H:%M")
        body = item.get("body", "")[:200].replace("<", "&lt;")
        url  = item.get("url", "#")

        # crude sentiment
        pos_words = ["surge", "bull", "breakout", "rally", "gain", "high", "rise", "pump", "buy", "adoption"]
        neg_words = ["crash", "bear", "drop", "fall", "sell", "hack", "fear", "loss", "ban", "dump"]
        tl = title.lower()
        if any(w in tl for w in pos_words):
            sent = '<span class="sentiment-pos">▲ Bullish</span>'
        elif any(w in tl for w in neg_words):
            sent = '<span class="sentiment-neg">▼ Bearish</span>'
        else:
            sent = '<span class="sentiment-neu">● Neutral</span>'

        st.markdown(f"""
<div class="news-item">
  <div class="news-title"><a href="{url}" target="_blank" style="color:#e2e8f0;text-decoration:none;">{title}</a></div>
  <div class="news-meta">{source} · {ts} · {sent}</div>
  <div style="font-size:.82rem;color:#64748b;margin-top:6px;">{body}…</div>
</div>
""", unsafe_allow_html=True)
else:
    st.markdown("<p style='color:#475569'>No recent news found for this asset.</p>", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — TECHNICAL ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.markdown('<div class="section-title">03 · Technical Analysis</div>', unsafe_allow_html=True)

if ta:
    sig_html = signal_chip(ta["signal"])
    st.markdown(f"<div style='margin-bottom:20px'>Signal: &nbsp;{sig_html} &nbsp;&nbsp; Score: <code style='color:#ff6600'>{ta['score']:+d}</code></div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Moving Averages**")
        for label, val in [("MA 20", ta["ma20"]), ("MA 50", ta.get("ma50")), ("MA 200", ta.get("ma200"))]:
            if val:
                above = price > val
                color = "#22c55e" if above else "#ef4444"
                tag   = "above" if above else "below"
                st.markdown(f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1e2030'><span style='color:#94a3b8'>{label}</span><span style='color:{color}'>{fmt_price(val)} <small>({tag})</small></span></div>", unsafe_allow_html=True)

        st.markdown("<br>**Oscillators**", unsafe_allow_html=True)
        rsi = ta["rsi"]
        rsi_color = "#ef4444" if rsi > 70 else "#22c55e" if rsi < 30 else "#94a3b8"
        rsi_tag   = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
        st.markdown(f"""
<div class="ta-row">
  <div class="ta-label">RSI (14)</div>
  <div class="ta-bar-bg"><div class="ta-bar-fill" style="width:{min(rsi,100):.0f}%;background:{rsi_color}"></div></div>
  <div class="ta-val" style="color:{rsi_color}">{rsi:.1f}</div>
</div>""", unsafe_allow_html=True)

        adx = ta["adx"]
        adx_pct = min(adx, 100)
        st.markdown(f"""
<div class="ta-row">
  <div class="ta-label">ADX (Trend)</div>
  <div class="ta-bar-bg"><div class="ta-bar-fill" style="width:{adx_pct:.0f}%;background:#818cf8"></div></div>
  <div class="ta-val">{adx:.1f}</div>
</div>""", unsafe_allow_html=True)

    with col2:
        st.markdown("**MACD**")
        macd_bull = ta["macd"] > ta["macd_sig"]
        st.markdown(f"""
<div style='background:#131620;border-radius:10px;padding:14px 16px;margin-bottom:12px'>
  <div style='display:flex;justify-content:space-between;margin-bottom:6px'>
    <span style='color:#94a3b8;font-size:.8rem'>MACD Line</span>
    <span style='font-family:JetBrains Mono,monospace;color:{"#22c55e" if ta["macd"]>0 else "#ef4444"}'>{ta["macd"]:.6f}</span>
  </div>
  <div style='display:flex;justify-content:space-between;margin-bottom:6px'>
    <span style='color:#94a3b8;font-size:.8rem'>Signal Line</span>
    <span style='font-family:JetBrains Mono,monospace;color:#94a3b8'>{ta["macd_sig"]:.6f}</span>
  </div>
  <div style='font-size:.8rem;color:{"#22c55e" if macd_bull else "#ef4444"}'>
    {"▲ Bullish crossover" if macd_bull else "▼ Bearish crossover"}
  </div>
</div>""", unsafe_allow_html=True)

        st.markdown("**Bollinger Bands**")
        bb_pct = (price - ta["bb_lo"]) / (ta["bb_up"] - ta["bb_lo"]) * 100 if ta["bb_up"] != ta["bb_lo"] else 50
        bb_pct = max(0, min(100, bb_pct))
        st.markdown(f"""
<div style='background:#131620;border-radius:10px;padding:14px 16px;margin-bottom:12px'>
  <div style='display:flex;justify-content:space-between;margin-bottom:8px'>
    <span style='color:#94a3b8;font-size:.8rem'>Upper</span><span style='font-family:JetBrains Mono,monospace;font-size:.85rem'>{fmt_price(ta["bb_up"])}</span>
  </div>
  <div class="ta-bar-bg"><div class="ta-bar-fill" style="width:{bb_pct:.0f}%;background:#ff6600"></div></div>
  <div style='display:flex;justify-content:space-between;margin-top:8px'>
    <span style='color:#94a3b8;font-size:.8rem'>Lower</span><span style='font-family:JetBrains Mono,monospace;font-size:.85rem'>{fmt_price(ta["bb_lo"])}</span>
  </div>
</div>""", unsafe_allow_html=True)

        st.markdown("**Volume & Volatility**")
        vol_color = "#22c55e" if ta["vol_ratio"] > 1.5 else "#94a3b8"
        st.markdown(f"""
<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1e2030'>
  <span style='color:#94a3b8;font-size:.85rem'>Vol Surge Ratio</span>
  <span style='color:{vol_color};font-family:JetBrains Mono,monospace'>{ta["vol_ratio"]:.2f}x</span>
</div>
<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1e2030'>
  <span style='color:#94a3b8;font-size:.85rem'>ATR (14)</span>
  <span style='font-family:JetBrains Mono,monospace;color:#e2e8f0'>{fmt_price(ta["atr"])}</span>
</div>
<div style='display:flex;justify-content:space-between;padding:6px 0'>
  <span style='color:#94a3b8;font-size:.85rem'>Z-Score (20d)</span>
  <span style='font-family:JetBrains Mono,monospace;color:{"#22c55e" if ta["zscore"]<-1 else "#ef4444" if ta["zscore"]>1 else "#94a3b8"}'>{ta["zscore"]:.2f}</span>
</div>""", unsafe_allow_html=True)

    # Price chart
    if not df_ohlcv.empty:
        st.markdown("<br>**Price Chart (90 days)**", unsafe_allow_html=True)
        chart_df = df_ohlcv[["close"]].tail(90).copy()
        chart_df.columns = ["Close Price"]
        st.line_chart(chart_df, color=["#ff6600"])
else:
    st.markdown("<p style='color:#475569'>Not enough OHLCV data for technical analysis.</p>", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — AI AGENT COUNCIL DEBATE
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.markdown('<div class="section-title">04 · AI Agent Council Debate</div>', unsafe_allow_html=True)

ta_summary = ""
if ta:
    ta_summary = f"""
Price: {fmt_price(ta['price'])} | Signal: {ta['signal']} | Score: {ta['score']:+d}
RSI: {ta['rsi']:.1f} | MACD: {'bullish' if ta['macd']>ta['macd_sig'] else 'bearish'}
ADX: {ta['adx']:.1f} | Vol surge: {ta['vol_ratio']:.2f}x | Z-score: {ta['zscore']:.2f}
BB Position: {'upper band' if ta['bb_up'] and price>ta['bb_up'] else 'lower band' if ta['bb_lo'] and price<ta['bb_lo'] else 'mid-range'}
"""

news_headlines = "\n".join([f"- {n.get('title','')}" for n in news_items[:5]])

ai_prompt = f"""You are a crypto investment council. Analyze {name} ({symbol}) and respond with exactly these 5 sections. Use the exact section headers shown.

MARKET DATA: {ta_summary if ta_summary else "Limited data"}
HEADLINES: {news_headlines if news_headlines else "No recent news"}

BULL_WHALE: [Write 2-3 bullish sentences about long-term thesis, adoption, and on-chain strength]

BEAR_TRADER: [Write 2-3 bearish sentences about risks, valuation concerns, and macro headwinds]

QUANT_ALGO: [Write 2-3 quantitative sentences about RSI={ta.get('rsi',0):.0f}, MACD trend, volume signals]

RISK_MANAGER: [Write 2-3 sentences on position sizing, suggested stop-loss, and risk/reward ratio]

VERDICT: [Write exactly 1 sentence with a clear buy/sell/hold recommendation and reasoning]"""

def parse_agent(text, key, next_keys):
    """Robustly extract agent section from AI output."""
    import re
    # Try multiple patterns: KEY:, **KEY**:, KEY\n, *KEY*
    patterns = [
        rf'{key}:\s*(.*?)(?=(?:{"|".join(next_keys)})[:\s]|\Z)',
        rf'\*\*{key}\*\*:?\s*(.*?)(?=(?:{"|".join(next_keys)})[:\s*]|\Z)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        if m:
            result = m.group(1).strip()
            # Clean up markdown artifacts
            result = re.sub(r'^\[|\]$', '', result).strip()
            result = re.sub(r'\*\*|\*|__', '', result).strip()
            if len(result) > 10:
                return result
    return None

if st.button("🤖 Run Agent Council Debate", use_container_width=False):
    with st.spinner("Convening the council…"):
        ai_output = run_gemini(ai_prompt)

    # Debug: show raw output in expander if all agents fail
    agent_keys = ["BULL_WHALE", "BEAR_TRADER", "QUANT_ALGO", "RISK_MANAGER", "VERDICT"]

    agents = {
        "BULL_WHALE":   ("🐋 Bull Whale",    "#0c1a2e", "#60a5fa"),
        "BEAR_TRADER":  ("🐻 Bear Trader",   "#1c0a0a", "#f87171"),
        "QUANT_ALGO":   ("🤖 Quant Algo",    "#0d0d1a", "#818cf8"),
        "RISK_MANAGER": ("🛡️ Risk Manager",  "#0a1a0a", "#4ade80"),
    }

    any_found = False
    for i, (key, (label, bg, color)) in enumerate(agents.items()):
        next_keys = agent_keys[i+1:]
        text = parse_agent(ai_output, key, next_keys)
        if text:
            any_found = True
        else:
            text = "_Agent did not respond._"
        st.markdown(f"""
<div class="agent-block" style="background:{bg};border-color:{color}30">
  <div class="agent-name" style="color:{color}">{label}</div>
  <div class="agent-text">{text}</div>
</div>""", unsafe_allow_html=True)

    # Verdict
    import re
    vm = re.search(r'VERDICT:?\s*(.*?)(?:\Z)', ai_output, re.DOTALL | re.IGNORECASE)
    verdict = vm.group(1).strip().split('\n')[0].strip() if vm else ""
    verdict = re.sub(r'^\[|\]$|\*\*|\*', '', verdict).strip()
    if not verdict:
        verdict = "The council could not reach a consensus — review the individual positions above."

    st.markdown(f"""
<div class="verdict-banner">
  <div class="verdict-label">⚖️ Council Verdict</div>
  <div class="verdict-text">{verdict}</div>
</div>""", unsafe_allow_html=True)

    # Show raw AI output if parsing completely failed
    if not any_found:
        with st.expander("⚠️ Raw AI output (parsing failed)"):
            st.text(ai_output)

else:
    st.markdown(f"<p style='color:#475569;font-size:.9rem'>Click the button above to trigger the AI council debate for {symbol}.</p>", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='text-align:center;margin-top:40px;padding-top:20px;border-top:1px solid #1e2030;color:#2a2d3e;font-size:.75rem;font-family:JetBrains Mono,monospace'>
  🔮 CRYPTO GURU · Not financial advice · DYOR always
</div>
""", unsafe_allow_html=True)
