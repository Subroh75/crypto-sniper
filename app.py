# ╔══════════════════════════════════════════════════════════════════╗
# ║  CRYPTO GURU — Intelligence Terminal v3.0                       ║
# ║  Search → Overview · News · TA · AI Council (auto-runs)        ║
# ║  Data: CryptoCompare · News: RSS + AI  ·  AI: Anthropic Claude ║
# ╚══════════════════════════════════════════════════════════════════╝

import streamlit as st
import pandas as pd
import numpy as np
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

st.set_page_config(
    page_title="Crypto Guru · Intelligence Terminal",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600;700&display=swap');
html, body, .stApp { background: #0a0a0f !important; color: #e2e8f0; font-family: 'Inter', sans-serif; }
section[data-testid="stSidebar"] { display: none !important; }
.block-container { max-width: 960px; margin: 0 auto; padding: 2rem 1.5rem; }
.hero { background: #0d0d14; border: 1px solid #1e2030; border-radius: 16px; padding: 36px 32px 28px; text-align: center; margin-bottom: 28px; }
.hero-title { font-family: 'JetBrains Mono', monospace; font-size: 2.2rem; font-weight: 700; color: #ff6600; margin-bottom: 6px; }
.hero-sub { font-size: 0.95rem; color: #64748b; }
.stTextInput > div > div > input { background: #0d1117 !important; border: 1px solid #2a2d3e !important; border-radius: 10px !important; color: #e2e8f0 !important; font-family: 'JetBrains Mono', monospace !important; font-size: 1.05rem !important; padding: 12px 18px !important; text-align: center; }
.stTextInput > div > div > input:focus { border-color: #ff6600 !important; box-shadow: 0 0 0 3px #ff660020 !important; }
.stTextInput label { display: none !important; }
.stButton > button { background: linear-gradient(135deg, #ff6600, #ff8c00) !important; color: #fff !important; border: none !important; border-radius: 8px !important; font-weight: 600 !important; padding: 10px 24px !important; }
.card { background: #0d1117; border: 1px solid #1e2030; border-radius: 12px; padding: 20px 24px; margin-bottom: 16px; }
.sec-title { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #ff6600; margin-bottom: 14px; }
.coin-name { font-size: 1.6rem; font-weight: 700; color: #e2e8f0; }
.coin-price { font-family: 'JetBrains Mono', monospace; font-size: 1.8rem; font-weight: 700; color: #e2e8f0; }
.chg-pos { color: #22c55e; } .chg-neg { color: #ef4444; }
.metric-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px; }
.metric-box { background: #131620; border: 1px solid #1e2030; border-radius: 8px; padding: 12px 14px; }
.metric-label { font-size: 0.65rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 3px; }
.metric-val { font-family: 'JetBrains Mono', monospace; font-size: 1rem; font-weight: 600; color: #e2e8f0; }
.news-item { border-left: 3px solid #ff6600; padding: 10px 14px; margin-bottom: 10px; background: #131620; border-radius: 0 8px 8px 0; }
.news-title a { color: #e2e8f0; text-decoration: none; font-size: 0.9rem; font-weight: 500; }
.news-title a:hover { color: #ff6600; }
.news-meta { font-size: 0.72rem; color: #475569; margin-top: 3px; }
.sent-pos { color: #22c55e; } .sent-neg { color: #ef4444; } .sent-neu { color: #94a3b8; }
.sig-chip { display: inline-block; padding: 5px 14px; border-radius: 20px; font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.08em; }
.chip-buy { background: #14532d; color: #4ade80; border: 1px solid #166534; }
.chip-sell { background: #450a0a; color: #f87171; border: 1px solid #7f1d1d; }
.chip-hold { background: #1c1917; color: #fbbf24; border: 1px solid #44403c; }
.chip-acc { background: #0c1a2e; color: #60a5fa; border: 1px solid #1e3a5f; }
.ta-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.ta-label { font-size: 0.75rem; color: #94a3b8; width: 110px; flex-shrink: 0; }
.ta-bar-bg { flex: 1; height: 5px; background: #1e2030; border-radius: 3px; }
.ta-bar-fill { height: 100%; border-radius: 3px; }
.ta-val { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #e2e8f0; width: 55px; text-align: right; }
.agent-msg { background: #0d1117; border-left: 3px solid #ff6600; border-radius: 0 8px 8px 0; padding: 12px 16px; margin-bottom: 10px; color: #cccccc; font-size: 0.875rem; line-height: 1.7; }
.agent-name { font-size: 0.68rem; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 6px; font-family: 'JetBrains Mono', monospace; }
.verdict-box { background: #0f1f10; border: 1px solid #166534; border-radius: 10px; padding: 16px 20px; text-align: center; margin-top: 14px; }
.verdict-label { font-size: 0.65rem; color: #4ade80; text-transform: uppercase; letter-spacing: 0.12em; margin-bottom: 6px; }
.verdict-text { font-size: 1rem; font-weight: 600; color: #e2e8f0; line-height: 1.5; }
hr { border-color: #1e2030 !important; }
.stSpinner > div { border-top-color: #ff6600 !important; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
CC_BASE       = "https://min-api.cryptocompare.com/data"
CC_KEY        = st.secrets.get("CRYPTOCOMPARE_API_KEY", "")
ANTHROPIC_KEY = st.secrets.get("ANTHROPIC_API_KEY", "")

def cc_headers():
    h = {"Content-Type": "application/json"}
    if CC_KEY:
        h["authorization"] = f"Apikey {CC_KEY}"
    return h

# ── Price / Info / OHLCV (unchanged) ─────────────────────────────────────────
@st.cache_data(ttl=120)
def get_price(symbol):
    try:
        r = requests.get(f"{CC_BASE}/pricemultifull?fsyms={symbol}&tsyms=USD", headers=cc_headers(), timeout=8)
        raw = r.json().get("RAW", {}).get(symbol, {}).get("USD", {})
        return {
            "price": raw.get("PRICE", 0), "chg24": raw.get("CHANGEPCT24HOUR", 0),
            "chg7d": raw.get("CHANGE7DAYSPCT", 0), "high24": raw.get("HIGH24HOUR", 0),
            "low24": raw.get("LOW24HOUR", 0), "vol24": raw.get("VOLUME24HOURTO", 0),
            "mktcap": raw.get("MKTCAP", 0), "supply": raw.get("SUPPLY", 0),
            "imgurl": "https://www.cryptocompare.com" + raw.get("IMAGEURL", ""),
        }
    except: return {}

@st.cache_data(ttl=300)
def get_info(symbol):
    try:
        r = requests.get(f"https://min-api.cryptocompare.com/data/coin/generalinfo?fsym={symbol}&tsym=USD", headers=cc_headers(), timeout=8)
        ci = r.json().get("Data", {}).get("CoinInfo", {})
        return {
            "name": ci.get("FullName", symbol), "algorithm": ci.get("Algorithm", "N/A"),
            "proof": ci.get("ProofType", "N/A"), "launch": ci.get("AssetLaunchDate", "N/A"),
            "desc": ci.get("Description", ""), "website": ci.get("Website", ""),
            "twitter": ci.get("Twitter", ""), "reddit": ci.get("Reddit", ""),
        }
    except: return {}

@st.cache_data(ttl=300)
def get_ohlcv(symbol, limit=100):
    try:
        r = requests.get(f"{CC_BASE}/v2/histoday?fsym={symbol}&tsym=USD&limit={limit}", headers=cc_headers(), timeout=10)
        data = r.json().get("Data", {}).get("Data", [])
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        return df.set_index("time")[["open", "high", "low", "close", "volumeto"]].rename(columns={"volumeto": "volume"})
    except: return pd.DataFrame()

# ── News: RSS feeds (no key needed) + AI summary fallback ────────────────────
RSS_FEEDS = [
    ("CoinDesk",    "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph","https://cointelegraph.com/rss"),
    ("Decrypt",     "https://decrypt.co/feed"),
    ("The Block",   "https://www.theblock.co/rss.xml"),
    ("Bitcoin Mag", "https://bitcoinmagazine.com/feed"),
]

@st.cache_data(ttl=300)
def get_news(symbol, coin_name=""):
    """Parse RSS feeds, filter by symbol/name, fallback to AI-generated context."""
    articles = []
    search_terms = [symbol.lower(), coin_name.lower()] if coin_name else [symbol.lower()]
    # Add common aliases
    aliases = {"XRP": ["ripple", "xrp"], "BTC": ["bitcoin", "btc"], "ETH": ["ethereum", "eth"],
               "SOL": ["solana", "sol"], "DOGE": ["dogecoin", "doge"], "ADA": ["cardano", "ada"],
               "DOT": ["polkadot", "dot"], "MATIC": ["polygon", "matic"], "AVAX": ["avalanche", "avax"],
               "LINK": ["chainlink", "link"], "UNI": ["uniswap", "uni"], "BNB": ["binance", "bnb"]}
    search_terms = list(set(search_terms + aliases.get(symbol.upper(), [])))

    for source_name, feed_url in RSS_FEEDS:
        if len(articles) >= 8:
            break
        try:
            r = requests.get(feed_url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            # Try RSS format
            items = root.findall(".//item")
            # Try Atom format
            if not items:
                items = root.findall(".//atom:entry", ns)
            for item in items:
                title = (item.findtext("title") or item.findtext("atom:title", namespaces=ns) or "").strip()
                link  = (item.findtext("link") or item.findtext("atom:link", namespaces=ns) or "").strip()
                pub   = (item.findtext("pubDate") or item.findtext("atom:published", namespaces=ns) or "").strip()
                desc  = (item.findtext("description") or item.findtext("atom:summary", namespaces=ns) or "").strip()
                # Filter to relevant articles
                combined = (title + " " + desc).lower()
                if any(term in combined for term in search_terms):
                    # Parse date
                    pub_fmt = ""
                    for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z"]:
                        try:
                            pub_fmt = datetime.strptime(pub[:25], fmt[:len(pub[:25])]).strftime("%b %d, %H:%M")
                            break
                        except: pass
                    articles.append({
                        "title": title, "url": link, "source": source_name,
                        "published": pub_fmt or pub[:16], "body": desc[:200].replace("<p>","").replace("</p>","").strip(),
                    })
                if len(articles) >= 8:
                    break
        except: continue

    return articles

def get_ai_news(symbol, coin_name, price_data, anthropic_key):
    """Use Claude to generate current news context when RSS finds nothing."""
    if not anthropic_key:
        return []
    pr = price_data.get("price", 0)
    c24 = price_data.get("chg24", 0)
    prompt = f"""You are a crypto market analyst. Today is {datetime.now().strftime('%B %d, %Y')}.

{coin_name} ({symbol}) is currently trading at ${pr:,.4f}, {'+' if c24>=0 else ''}{c24:.2f}% in 24h.

List 5 recent news headlines and brief summaries about {symbol} that would be relevant to traders right now. Include regulatory news, adoption, technical developments, and market sentiment. Format each as:

HEADLINE: [title]
SOURCE: [news source name]
SUMMARY: [1-2 sentence summary]
SENTIMENT: [BULLISH/BEARISH/NEUTRAL]
---"""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 800, "messages": [{"role": "user", "content": prompt}]},
            timeout=20,
        )
        text = resp.json()["content"][0]["text"]
        # Parse the structured output
        articles = []
        blocks = text.split("---")
        for block in blocks:
            if "HEADLINE:" not in block: continue
            lines = {l.split(":", 1)[0].strip(): l.split(":", 1)[1].strip() for l in block.strip().split("\n") if ":" in l}
            title = lines.get("HEADLINE", "")
            if title:
                articles.append({
                    "title": title, "url": "#", "source": lines.get("SOURCE", "AI Analysis"),
                    "published": datetime.now().strftime("%b %d"), "body": lines.get("SUMMARY", ""),
                    "ai_sentiment": lines.get("SENTIMENT", "NEUTRAL"),
                })
        return articles[:6]
    except: return []

# ── Technical Analysis ────────────────────────────────────────────────────────
def compute_ta(df):
    if df.empty or len(df) < 20: return {}
    c, v = df["close"], df["volume"]
    sma = lambda s, n: s.rolling(n).mean()
    ema = lambda s, n: s.ewm(span=n, adjust=False).mean()
    price = c.iloc[-1]
    ma20  = float(sma(c, 20).iloc[-1])
    ma50  = float(sma(c, 50).iloc[-1]) if len(c) >= 50 else None
    ma200 = float(sma(c, 200).iloc[-1]) if len(c) >= 200 else None
    delta = c.diff(); gain = delta.clip(lower=0).rolling(14).mean(); loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi   = float((100 - 100 / (1 + gain / loss.replace(0, 0.000001))).iloc[-1])
    ml = ema(c, 12) - ema(c, 26); sl = ema(ml, 9)
    macd = float(ml.iloc[-1]); msig = float(sl.iloc[-1])
    bb_std = c.rolling(20).std()
    bb_up = float((sma(c, 20) + 2*bb_std).iloc[-1]); bb_lo = float((sma(c, 20) - 2*bb_std).iloc[-1])
    hl = df["high"]-df["low"]; hc = (df["high"]-c.shift()).abs(); lc = (df["low"]-c.shift()).abs()
    atr  = float(pd.concat([hl,hc,lc],axis=1).max(axis=1).rolling(14).mean().iloc[-1])
    pdm  = df["high"].diff().clip(lower=0); mdm = -df["low"].diff().clip(upper=0)
    adx  = float((abs(pdm.rolling(14).sum()-mdm.rolling(14).sum())/hl.rolling(14).sum().replace(0,0.000001)*100).rolling(14).mean().iloc[-1])
    avg_v = float(v.rolling(20).mean().iloc[-1]); vr = float(v.iloc[-1])/avg_v if avg_v>0 else 1
    z    = float((price-float(sma(c,20).iloc[-1]))/float(c.rolling(20).std().iloc[-1]))
    score = int(price>ma20)+int(bool(ma50) and price>ma50)+int(bool(ma200) and price>ma200)
    if rsi<30: score+=2
    elif rsi>70: score-=2
    score += int(macd>msig)+int(vr>1.5)+int(z<-1.5); score -= int(z>1.5)
    sig = "STRONG BUY" if score>=5 else "ACCUMULATE" if score>=3 else "STRONG SELL" if score<=-3 else "CAUTION" if score<=-1 else "NEUTRAL"
    return {"price":price,"ma20":ma20,"ma50":ma50,"ma200":ma200,"rsi":rsi,"macd":macd,"msig":msig,
            "bb_up":bb_up,"bb_lo":bb_lo,"atr":atr,"adx":adx,"vr":vr,"z":z,"signal":sig,"score":score}

# ── AI Council ────────────────────────────────────────────────────────────────
def run_council(name, symbol, ta, news_items):
    if not ANTHROPIC_KEY:
        return None, "Add ANTHROPIC_API_KEY to Streamlit secrets."
    ta_str = f"Price: ${ta['price']:,.4f} | Signal: {ta['signal']} | Score: {ta['score']:+d} | RSI: {ta['rsi']:.1f} | MACD: {'bullish' if ta['macd']>ta['msig'] else 'bearish'} | ADX: {ta['adx']:.1f} | Vol surge: {ta['vr']:.2f}x | Z-score: {ta['z']:.2f}" if ta else "Limited data"
    headlines = " | ".join([n.get("title","") for n in news_items[:5]]) if news_items else "No recent news"
    prompt = f"""You are a crypto investment council. Analyze {name} ({symbol}) and give each member's view.

Technical snapshot: {ta_str}
Recent news: {headlines}

Write each agent's perspective. Use these EXACT labels as section headers (on their own line):

BULL WHALE
BEAR TRADER
QUANT ALGO
RISK MANAGER
VERDICT

Each section: 2-3 sentences. VERDICT: one clear actionable sentence."""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 900,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=30,
        )
        return resp.json()["content"][0]["text"], None
    except Exception as e:
        return None, str(e)

def parse_council(text):
    labels = ["BULL WHALE", "BEAR TRADER", "QUANT ALGO", "RISK MANAGER", "VERDICT"]
    result = {}
    current = None
    buf = []
    for line in text.split("\n"):
        s = line.strip()
        # Check if line IS a label (exact match or starts with label)
        matched = next((l for l in labels if s.upper() == l or s.upper().startswith(l + ":") or s.upper().replace("**","").strip() == l), None)
        if matched:
            if current and buf:
                result[current] = " ".join(b for b in buf if b).strip()
            current = matched
            # Grab anything after the colon on the same line
            remainder = s[len(matched):].lstrip(": *").strip()
            buf = [remainder] if remainder else []
        elif current and s:
            buf.append(s)
    if current and buf:
        result[current] = " ".join(b for b in buf if b).strip()
    return result

# ── Helpers ───────────────────────────────────────────────────────────────────
def fp(n):
    return f"${n:,.2f}" if n>=1000 else f"${n:.4f}" if n>=1 else f"${n:.8f}"

def fl(n):
    if n>=1e12: return f"${n/1e12:.2f}T"
    if n>=1e9:  return f"${n/1e9:.2f}B"
    if n>=1e6:  return f"${n/1e6:.2f}M"
    return f"${n:,.0f}"

def chg_html(v):
    cls = "chg-pos" if v>=0 else "chg-neg"
    return f'<span class="{cls}">{("+" if v>=0 else "")}{v:.2f}%</span>'

def sig_chip(s):
    m = {"STRONG BUY":"chip-buy","ACCUMULATE":"chip-acc","NEUTRAL":"chip-hold","CAUTION":"chip-hold","STRONG SELL":"chip-sell"}
    css = m.get(s, "chip-hold")
    return f'<span class="sig-chip {css}">{s}</span>'

def sent_tag(title, ai_sent=None):
    if ai_sent:
        if ai_sent == "BULLISH": return '<span class="sent-pos">▲ Bullish</span>'
        if ai_sent == "BEARISH": return '<span class="sent-neg">▼ Bearish</span>'
        return '<span class="sent-neu">● Neutral</span>'
    pos = ["surge","bull","breakout","rally","gain","rise","pump","buy","adoption","approved","launch","partnership","win","ruling","etf"]
    neg = ["crash","bear","drop","fall","sell","hack","fear","loss","ban","dump","fraud","sued","warning","reject","delay"]
    tl = title.lower()
    if any(w in tl for w in pos): return '<span class="sent-pos">▲ Bullish</span>'
    if any(w in tl for w in neg): return '<span class="sent-neg">▼ Bearish</span>'
    return '<span class="sent-neu">● Neutral</span>'

# ── UI ────────────────────────────────────────────────────────────────────────
st.markdown('<div class="hero"><div class="hero-title">🔮 CRYPTO GURU</div><div class="hero-sub">Intelligence Terminal · Enter any crypto ticker to begin</div></div>', unsafe_allow_html=True)

col_s, col_b = st.columns([5, 1])
with col_s:
    query = st.text_input("", placeholder="BTC · ETH · SOL · XRP · DOGE · PEPE · any ticker...", key="q")
with col_b:
    st.button("Analyse", use_container_width=True)

symbol = query.strip().upper() if query else ""

if not symbol:
    st.markdown('<div style="text-align:center;margin-top:60px;color:#1e2030;font-size:3rem;">🔮</div>', unsafe_allow_html=True)
    st.stop()

# ── Fetch ─────────────────────────────────────────────────────────────────────
with st.spinner(f"Loading {symbol}…"):
    price_data = get_price(symbol)
    coin_info  = get_info(symbol)
    df_ohlcv   = get_ohlcv(symbol)
    ta         = compute_ta(df_ohlcv)
    name       = coin_info.get("name") or symbol
    # News: RSS first, AI fallback if nothing found
    news_items = get_news(symbol, name)
    using_ai_news = False
    if not news_items and ANTHROPIC_KEY:
        news_items = get_ai_news(symbol, name, price_data, ANTHROPIC_KEY)
        using_ai_news = True

if not price_data or price_data.get("price", 0) == 0:
    st.error(f"⚠️ No data found for **{symbol}**. Check the ticker and try again.")
    st.stop()

pr  = price_data["price"]
c24 = price_data["chg24"]
c7d = price_data["chg7d"]

# ── SECTION 1: Overview ───────────────────────────────────────────────────────
st.markdown('<div class="card">', unsafe_allow_html=True)
st.markdown('<div class="sec-title">01 · Project Overview</div>', unsafe_allow_html=True)
st.markdown(f"""
<div style="display:flex;align-items:center;gap:18px;margin-bottom:16px">
  <img src="{price_data['imgurl']}" style="width:56px;height:56px;border-radius:50%" onerror="this.style.display='none'"/>
  <div>
    <div class="coin-name">{name}</div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:.85rem;color:#64748b">{symbol} · {coin_info.get('algorithm','N/A')} · {coin_info.get('proof','N/A')}</div>
  </div>
  <div style="margin-left:auto;text-align:right">
    <div class="coin-price">{fp(pr)}</div>
    <div>{chg_html(c24)} 24h &nbsp; {chg_html(c7d)} 7d</div>
  </div>
</div>
<div class="metric-grid">
  <div class="metric-box"><div class="metric-label">Market Cap</div><div class="metric-val">{fl(price_data['mktcap'])}</div></div>
  <div class="metric-box"><div class="metric-label">24h Volume</div><div class="metric-val">{fl(price_data['vol24'])}</div></div>
  <div class="metric-box"><div class="metric-label">Supply</div><div class="metric-val">{fl(price_data['supply'])}</div></div>
  <div class="metric-box"><div class="metric-label">24h High</div><div class="metric-val">{fp(price_data['high24'])}</div></div>
  <div class="metric-box"><div class="metric-label">24h Low</div><div class="metric-val">{fp(price_data['low24'])}</div></div>
  <div class="metric-box"><div class="metric-label">Launch</div><div class="metric-val">{coin_info.get('launch','N/A')}</div></div>
</div>""", unsafe_allow_html=True)
desc = coin_info.get("desc", "")
if desc:
    st.markdown(f"<p style='margin-top:14px;font-size:.88rem;color:#94a3b8;line-height:1.7'>{desc[:700]}{'…' if len(desc)>700 else ''}</p>", unsafe_allow_html=True)
links = []
if coin_info.get("website"): links.append(f"[🌐 Website]({coin_info['website']})")
if coin_info.get("twitter"):  links.append(f"[🐦 Twitter]({coin_info['twitter']})")
if coin_info.get("reddit"):   links.append(f"[🔴 Reddit]({coin_info['reddit']})")
if links: st.markdown("  ·  ".join(links))
st.markdown('</div>', unsafe_allow_html=True)

# ── SECTION 2: News ───────────────────────────────────────────────────────────
st.markdown('<div class="card">', unsafe_allow_html=True)
news_label = f"02 · News & Sentiment {'· AI-Generated Context' if using_ai_news else '· Live RSS Feeds'}"
st.markdown(f'<div class="sec-title">{news_label}</div>', unsafe_allow_html=True)

if news_items:
    for item in news_items:
        title    = item.get("title","")
        url      = item.get("url","#")
        src      = item.get("source","")
        pub      = item.get("published","")
        body     = item.get("body","")
        ai_sent  = item.get("ai_sentiment")
        link_tag = f'<a href="{url}" target="_blank">{title}</a>' if url != "#" else title
        st.markdown(f"""
<div class="news-item">
  <div class="news-title">{link_tag}</div>
  <div class="news-meta">{src} · {pub} · {sent_tag(title, ai_sent)}</div>
  {f"<div style='font-size:.78rem;color:#64748b;margin-top:5px'>{body[:200]}</div>" if body else ""}
</div>""", unsafe_allow_html=True)
else:
    st.markdown(f"<p style='color:#475569;font-size:.88rem'>No recent {symbol} news found in RSS feeds. Add ANTHROPIC_API_KEY to secrets to enable AI-generated news context.</p>", unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ── SECTION 3: Technical Analysis ─────────────────────────────────────────────
st.markdown('<div class="card">', unsafe_allow_html=True)
st.markdown('<div class="sec-title">03 · Technical Analysis</div>', unsafe_allow_html=True)
if ta:
    st.markdown(f"<div style='margin-bottom:16px'>Signal: &nbsp;{sig_chip(ta['signal'])} &nbsp;&nbsp; Score: <code style='color:#ff6600'>{ta['score']:+d}/8</code></div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Moving Averages**")
        for lb, val in [("MA 20", ta["ma20"]), ("MA 50", ta.get("ma50")), ("MA 200", ta.get("ma200"))]:
            if val:
                ab = pr>val; col = "#22c55e" if ab else "#ef4444"; tag = "above" if ab else "below"
                st.markdown(f"<div style='display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #1e2030'><span style='color:#94a3b8;font-size:.82rem'>{lb}</span><span style='color:{col};font-size:.82rem'>{fp(val)} <small>({tag})</small></span></div>", unsafe_allow_html=True)
        rsi=ta["rsi"]; rc="#ef4444" if rsi>70 else "#22c55e" if rsi<30 else "#94a3b8"
        st.markdown(f"<br><div class='ta-row'><div class='ta-label'>RSI (14)</div><div class='ta-bar-bg'><div class='ta-bar-fill' style='width:{min(rsi,100):.0f}%;background:{rc}'></div></div><div class='ta-val' style='color:{rc}'>{rsi:.1f}</div></div>", unsafe_allow_html=True)
        adx=ta["adx"]
        st.markdown(f"<div class='ta-row'><div class='ta-label'>ADX</div><div class='ta-bar-bg'><div class='ta-bar-fill' style='width:{min(adx,100):.0f}%;background:#818cf8'></div></div><div class='ta-val'>{adx:.1f}</div></div>", unsafe_allow_html=True)
    with col2:
        mb=ta["macd"]>ta["msig"]
        st.markdown(f"**MACD** {'▲ Bullish' if mb else '▼ Bearish'}")
        st.markdown(f"<div style='background:#131620;border-radius:8px;padding:12px 14px;margin-bottom:10px;font-size:.82rem'><div style='display:flex;justify-content:space-between;margin-bottom:5px'><span style='color:#94a3b8'>MACD</span><span style='color:{'#22c55e' if ta['macd']>0 else '#ef4444'};font-family:monospace'>{ta['macd']:.6f}</span></div><div style='display:flex;justify-content:space-between'><span style='color:#94a3b8'>Signal</span><span style='font-family:monospace;color:#94a3b8'>{ta['msig']:.6f}</span></div></div>", unsafe_allow_html=True)
        bb_pct=max(0,min(100,(pr-ta["bb_lo"])/(ta["bb_up"]-ta["bb_lo"])*100)) if ta["bb_up"]!=ta["bb_lo"] else 50
        st.markdown(f"**Bollinger Bands**")
        st.markdown(f"<div style='background:#131620;border-radius:8px;padding:12px 14px;margin-bottom:10px;font-size:.82rem'><div style='display:flex;justify-content:space-between;margin-bottom:7px'><span style='color:#94a3b8'>Upper</span><span style='font-family:monospace'>{fp(ta['bb_up'])}</span></div><div class='ta-bar-bg'><div class='ta-bar-fill' style='width:{bb_pct:.0f}%;background:#ff6600'></div></div><div style='display:flex;justify-content:space-between;margin-top:7px'><span style='color:#94a3b8'>Lower</span><span style='font-family:monospace'>{fp(ta['bb_lo'])}</span></div></div>", unsafe_allow_html=True)
        vc="#22c55e" if ta["vr"]>1.5 else "#94a3b8"
        st.markdown(f"<div style='font-size:.82rem'><div style='display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #1e2030'><span style='color:#94a3b8'>Vol surge</span><span style='color:{vc};font-family:monospace'>{ta['vr']:.2f}x</span></div><div style='display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #1e2030'><span style='color:#94a3b8'>ATR (14)</span><span style='font-family:monospace'>{fp(ta['atr'])}</span></div><div style='display:flex;justify-content:space-between;padding:5px 0'><span style='color:#94a3b8'>Z-score</span><span style='color:{'#22c55e' if ta['z']<-1 else '#ef4444' if ta['z']>1 else '#94a3b8'};font-family:monospace'>{ta['z']:.2f}</span></div></div>", unsafe_allow_html=True)
    if not df_ohlcv.empty:
        st.markdown("<br>**Price Chart (90 days)**", unsafe_allow_html=True)
        ch = df_ohlcv[["close"]].tail(90).copy(); ch.columns=["Close"]; st.line_chart(ch, color=["#ff6600"])
else:
    st.markdown("<p style='color:#475569'>Insufficient OHLCV data for TA.</p>", unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ── SECTION 4: AI Council (auto-runs) ─────────────────────────────────────────
st.markdown('<div class="card">', unsafe_allow_html=True)
st.markdown('<div class="sec-title">04 · AI Agent Council Debate</div>', unsafe_allow_html=True)

if not ANTHROPIC_KEY:
    st.markdown("<p style='color:#475569;font-size:.88rem'>Add ANTHROPIC_API_KEY to Streamlit secrets to enable the AI council.</p>", unsafe_allow_html=True)
else:
    with st.spinner("Convening the council…"):
        council_text, err = run_council(name, symbol, ta, news_items)

    if err:
        st.error(f"Council error: {err}")
    elif council_text:
        parsed = parse_council(council_text)
        agents = [
            ("BULL WHALE",   "🐋 Bull Whale",   "#60a5fa"),
            ("BEAR TRADER",  "🐻 Bear Trader",  "#f87171"),
            ("QUANT ALGO",   "🤖 Quant Algo",   "#818cf8"),
            ("RISK MANAGER", "🛡️ Risk Manager", "#4ade80"),
        ]
        for key, label, color in agents:
            text = parsed.get(key, "")
            if text:
                st.markdown(f'<div class="agent-msg"><div class="agent-name" style="color:{color}">{label}</div>{text}</div>', unsafe_allow_html=True)

        verdict = parsed.get("VERDICT", "")
        if verdict:
            st.markdown(f'<div class="verdict-box"><div class="verdict-label">⚖️ Council Verdict</div><div class="verdict-text">{verdict}</div></div>', unsafe_allow_html=True)

        # Only show debug if completely empty
        if not parsed:
            st.markdown("**Debug — raw council output:**")
            st.text(council_text)

st.markdown('</div>', unsafe_allow_html=True)
st.markdown("<div style='text-align:center;margin-top:32px;color:#1e2030;font-size:.72rem;font-family:JetBrains Mono,monospace'>🔮 CRYPTO GURU · Not financial advice · DYOR</div>", unsafe_allow_html=True)
