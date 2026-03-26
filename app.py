# Crypto Sniper Elite v1.0 — CryptoCompare Edition
# Source: min-api.cryptocompare.com (from public-apis list) — No auth, 366 days OHLCV free
import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

st.set_page_config(page_title='Crypto Sniper Elite v1.0', layout='wide')

def get_ai_client():
    try:
        if GENAI_AVAILABLE and 'GEMINI_API_KEY' in st.secrets:
            genai.configure(api_key=st.secrets['GEMINI_API_KEY'])
            return genai.GenerativeModel('gemini-2.5-flash-preview-04-17')
        return None
    except Exception:
        return None
client = get_ai_client()

def highlight_reco(val):
    c = {'STRONG BUY':'#2ecc71','STRONG SELL':'#e74c3c',
         'REVERSION BUY':'#f39c12','ACCUMULATE':'#27ae60','NEUTRAL':'#f1c40f'}
    for k,v in c.items():
        if k in str(val): return f'background-color:{v};color:black;font-weight:bold'
    return ''

def safe_cols(frame, cols):
    return [c for c in cols if c in frame.columns]

CC = 'https://min-api.cryptocompare.com/data'
HDR = {'Accept':'application/json','User-Agent':'CryptoSniper/1.0'}

def cc_get(path, params=None, retries=3):
    for i in range(retries):
        try:
            r = requests.get(f'{CC}{path}', params=params, headers=HDR, timeout=20)
            if r.status_code == 200:
                d = r.json()
                if d.get('Response') == 'Error':
                    return None
                return d
        except Exception:
            pass
        time.sleep(1.5 * (i+1))
    return None

# ── STEP 1: TOP-500 UNIVERSE via CryptoCompare /top/mktcapfull ─────────────
# 100 coins per call with live price, 24h change, volume — 5 calls = 500 coins
@st.cache_data(ttl=300)
def get_universe(scan_n):
    coins = []
    pages = (min(scan_n, 500) + 99) // 100
    for page in range(pages):
        d = cc_get('/top/mktcapfull', {'limit':100,'tsym':'USD','page':page})
        if d and 'Data' in d:
            for c in d['Data']:
                info = c.get('CoinInfo', {})
                raw  = c.get('RAW', {}).get('USD', {})
                sym  = info.get('Name', '')
                if not sym or not raw.get('PRICE'): continue
                coins.append({
                    'sym':   sym,
                    'name':  info.get('FullName', sym),
                    'price': float(raw.get('PRICE') or 0),
                    'vol24': float(raw.get('VOLUME24HOURTO') or 0),
                    'chg24': float(raw.get('CHANGEPCT24HOUR') or 0),
                    'mcap':  float(raw.get('MKTCAP') or 0),
                })
        time.sleep(0.5)
    return coins

# ── STEP 2: 366-DAY DAILY OHLCV via CryptoCompare /v2/histoday ─────────────
# Confirmed working: returns open,high,low,close,volumefrom free, no auth
def fetch_ohlcv(sym):
    d = cc_get('/v2/histoday', {'fsym':sym,'tsym':'USD','limit':365})
    if not d or 'Data' not in d: return None
    candles = d['Data'].get('Data', [])
    if len(candles) < 30: return None
    df = pd.DataFrame(candles)
    df = df[df['close'] > 0].copy()
    df['close']  = pd.to_numeric(df['close'],  errors='coerce')
    df['high']   = pd.to_numeric(df['high'],   errors='coerce')
    df['low']    = pd.to_numeric(df['low'],    errors='coerce')
    df['volume'] = pd.to_numeric(df['volumefrom'], errors='coerce').fillna(1)
    df = df.dropna(subset=['close']).reset_index(drop=True)
    return df if len(df) >= 30 else None

# ── MATH ENGINE ─────────────────────────────────────────────────────────────
def calc(df, live_price, chg24, vol24):
    try:
        c = df['close'].values.astype(float)
        h = df['high'].values.astype(float)
        l = df['low'].values.astype(float)
        v = df['volume'].values.astype(float)
        n = min(len(c),len(h),len(l),len(v))
        c,h,l,v = c[-n:],h[-n:],l[-n:],v[-n:]
        if n < 30: return None
        c[-1] = live_price
        def sma(a,w): return float(pd.Series(a).rolling(w).mean().iloc[-1])
        m20  = sma(c,20)
        m50  = sma(c,50)  if n>=50  else float('nan')
        m200 = sma(c,200) if n>=200 else float('nan')
        tr   = np.maximum(h[1:]-l[1:],np.maximum(np.abs(h[1:]-c[:-1]),np.abs(l[1:]-c[:-1])))
        atr  = round(float(pd.Series(tr).rolling(14).mean().iloc[-1]),6)
        pdm  = np.where((h[1:]-h[:-1])>(l[:-1]-l[1:]),np.maximum(h[1:]-h[:-1],0),0)
        mdm  = np.where((l[:-1]-l[1:])>(h[1:]-h[:-1]),np.maximum(l[:-1]-l[1:],0),0)
        trs  = pd.Series(tr).rolling(14).mean()
        pdi  = 100*(pd.Series(pdm).rolling(14).mean()/(trs+1e-9))
        mdi  = 100*(pd.Series(mdm).rolling(14).mean()/(trs+1e-9))
        adx  = float((np.abs(pdi-mdi)/(pdi+mdi+1e-9)*100).rolling(14).mean().iloc[-1])
        z    = float((c[-1]-m20)/(np.std(c[-20:])+1e-9))
        vs   = float(v[-1]/(np.mean(v[-20:])+1e-9)) if v.mean()>0 else 1.0
        vs   = min(max(vs,0.1),20.0)
        p1   = chg24/100
        p7   = float((c[-1]-c[-7])/(c[-7]+1e-9))  if n>=7  else 0.0
        p30  = float((c[-1]-c[-30])/(c[-30]+1e-9)) if n>=30 else 0.0
        miro = 2+(5 if vs>2.0 else 0)+(3 if p1>0.01 else 0)
        if   p1> 0.02 and vs>1.5: sig='STRONG BUY'
        elif p1<-0.02 and vs>1.5: sig='STRONG SELL'
        elif z <-2.2:              sig='REVERSION BUY'
        elif not np.isnan(m200) and c[-1]>m200 and adx>25: sig='ACCUMULATE'
        else:                      sig='NEUTRAL'
        return dict(Price=round(float(c[-1]),6),MA20=round(m20,4),
                    MA50=round(m50,4) if not np.isnan(m50) else 'N/A',
                    MA200=round(m200,4) if not np.isnan(m200) else 'N/A',
                    ADX=round(adx,1),ZScore=round(z,2),VolSrg=round(vs,2),
                    ATR=atr,Chg24=round(p1*100,2),Chg7D=round(p7*100,2),
                    Chg30D=round(p30*100,2),Miro=miro,Signal=sig)
    except Exception: return None

# ── SIDEBAR ─────────────────────────────────────────────────────────────────
st.sidebar.title('Crypto Sniper v1.0')
st.sidebar.subheader(f"📅 {datetime.now().strftime('%b %d, %Y')} Pulse")

@st.cache_data(ttl=60)
def live_prices():
    d = cc_get('/price', {'fsym':'BTC','tsyms':'USD,ETH'})
    if d:
        btc = round(float(d.get('USD',0)),2)
        d2  = cc_get('/price', {'fsym':'ETH','tsyms':'USD'})
        eth = round(float((d2 or {}).get('USD',0)),2)
        return btc, eth
    return 'N/A','N/A'

btc_p,eth_p = live_prices()
st.sidebar.table(pd.DataFrame({'Metric':['BTC ($)','ETH ($)'],'Value':[str(btc_p),str(eth_p)]}))
scan_n = st.sidebar.slider('Scan Depth',10,500,50)
st.sidebar.caption('⚡ CryptoCompare: 100 coins/call bulk + 366d OHLCV per coin')
st.sidebar.caption('📡 No auth required · public-apis sourced')

# ── SCAN ────────────────────────────────────────────────────────────────────
if st.sidebar.button('🚀 EXECUTE FULL CRYPTO AUDIT'):
    bar  = st.progress(0.0, text='⚡ Fetching top coins from CryptoCompare…')
    stat = st.empty()
    universe = get_universe(scan_n)
    if not universe:
        st.error('CryptoCompare unavailable. Try again in 30s.')
        st.stop()
    coins = universe[:scan_n]
    bar.progress(0.1, text=f'✅ Got {len(coins)} coins! Fetching OHLCV for technicals…')
    rows, skipped = [], 0
    for i, coin in enumerate(coins):
        pct  = 0.1 + 0.9*((i+1)/len(coins))
        sym  = coin['sym']
        name = coin['name']
        price= coin['price']
        chg24= coin['chg24']
        vol24= coin['vol24']
        bar.progress(pct, text=f'🔬 {sym} ({i+1}/{len(coins)}) | {len(rows)} signals | {skipped} skipped')
        if price <= 0: skipped+=1; continue
        df = fetch_ohlcv(sym)
        time.sleep(0.3)
        if df is not None:
            m = calc(df, price, chg24, vol24)
            if m:
                rows.append({'Ticker':sym,'Name':name,**m})
                stat.success(f"✅ {sym} → {m['Signal']} | ${price:,.4g} | 24h:{chg24:+.1f}%")
            else:
                skipped+=1; stat.warning(f'⚠️ {sym} — calc failed')
        else:
            skipped+=1; stat.info(f'ℹ️ {sym} — no OHLCV (very new coin?)')
    bar.progress(1.0, text=f'✅ Done — {len(rows)} coins analysed | {skipped} skipped')
    if rows:
        st.session_state['res'] = pd.DataFrame(rows)
        st.session_state['btc'] = btc_p
        st.session_state['eth'] = eth_p
        st.rerun()
    else:
        st.error('No results. Try again in 30s.')

# ── RESULTS ─────────────────────────────────────────────────────────────────
if 'res' in st.session_state:
    df  = st.session_state['res']
    bpx = st.session_state.get('btc','N/A')
    epx = st.session_state.get('eth','N/A')
    df_n = df.copy()
    df_n['MA200n'] = pd.to_numeric(df_n['MA200'],errors='coerce')
    above = (df_n['MA200n'].notna()&(df_n['Price']>df_n['MA200n'])).sum()
    brd   = above/len(df)*100
    st.sidebar.markdown('---')
    st.sidebar.subheader('📊 Market Heatmap')
    if   brd>60: st.sidebar.success(f'🔥 BULL REGIME {round(brd,1)}%')
    elif brd<40: st.sidebar.error(  f'🧊 BEAR REGIME {round(brd,1)}%')
    else:        st.sidebar.warning(f'⚖️ NEUTRAL     {round(brd,1)}%')
    risk = st.sidebar.number_input('Risk Capital ($)',value=1000,step=100)
    df['StopLoss'] = df['Price']-2.0*df['ATR']
    df['Qty'] = (risk/(df['Price']-df['StopLoss'])).replace([np.inf,-np.inf],0).fillna(0).round(0).astype(int)

    T = st.tabs(['🎯 Miro Flow','📈 Trend & ADX','🔄 Reversion','💎 Weekly Sniper','📂 AI Audit','🧠 Council Debate'])
    def tbl(frame,cols):
        cols = safe_cols(frame, cols)
        st.dataframe(frame[cols].style.map(highlight_reco,subset=['Signal']),hide_index=True,use_container_width=True)

    with T[0]:
        st.subheader('🎯 Miro Momentum Leaderboard')
        st.caption('Hot-money detection — institutional flow entering NOW')
        tbl(df.sort_values('Miro',ascending=False),['Ticker','Name','Price','Signal','Miro','VolSrg','Chg24','Chg7D','Chg30D'])
        with st.expander('📘 Tactical Logic'):
            st.markdown('**Miro 2-10:** hot-money velocity. **VolSrg>2:** mass accumulation. **Edge:** early breakout warning.')
    with T[1]:
        st.subheader('📈 Trend Strength Leaderboard')
        st.caption('ADX>25 = trending | ADX>40 = explosive')
        tbl(df.sort_values('ADX',ascending=False),['Ticker','Name','Price','MA20','MA50','MA200','ADX','Signal'])
        with st.expander('📘 Tactical Logic'):
            st.markdown('**ADX>25:** ride the wave. **MA Stack 20>50>200:** highest-conviction bull zone.')
    with T[2]:
        st.subheader('🔄 Mean Reversion — Snap-Back Candidates')
        st.caption('Z-Score < -2.2 = statistically oversold')
        tbl(df.sort_values('ZScore',ascending=True),['Ticker','Name','Price','MA20','ZScore','ATR','Signal'])
        with st.expander('📘 Tactical Logic'):
            st.markdown('**Z<-2.2:** rubber band stretched. High prob snap-back to MA20 in 1-3 sessions.')
    with T[3]:
        st.subheader('💎 Weekly Institutional Flow')
        st.caption('Where whales are building walls — sorted by volume surge')
        tbl(df.sort_values('VolSrg',ascending=False),['Ticker','Name','Price','Signal','VolSrg','Chg24','Chg7D','Chg30D'])
        with st.expander('📘 Tactical Logic'):
            st.markdown('**VolSrg>2:** institution absorbing sellers. Small price + massive vol = breakout incoming.')
    with T[4]:
        st.subheader('📂 AI Audit')
        pick = st.selectbox('Select asset',df['Ticker'].tolist(),key='a_pick')
        row  = df[df['Ticker']==pick].to_dict('records')
        row  = row[0] if row else {}
        if st.button('🔍 Run AI Audit',key='btn_audit'):
            if client:
                p = (f"Today is {datetime.now().strftime('%B %d, %Y')}. "
                     f"Senior crypto analyst audit for {row.get('Name',pick)} ({pick}). "
                     f"Scanner data: {row}. BTC=${bpx}, ETH=${epx}. "
                     f"Cover: 1)On-chain 2)Macro 3)Technicals 4)Catalysts 5)Institutional. BUY/HOLD/SELL verdict.")
                with st.spinner('Analysing…'):
                    try: st.markdown(client.generate_content(p).text)
                    except Exception as ex: st.error(f'AI error: {ex}')
            else:
                st.info('Add GEMINI_API_KEY to Streamlit secrets.')
                st.json(row)
    with T[5]:
        st.subheader('🧠 Council Debate')
        pick2 = st.selectbox('Select asset',df['Ticker'].tolist(),key='d_pick')
        row2  = df[df['Ticker']==pick2].to_dict('records')
        row2  = row2[0] if row2 else {}
        if st.button('🤖 Summon Council',key='btn_debate'):
            if client:
                p2 = (f"Today is {datetime.now().strftime('%B %d, %Y')}. "
                      f"4-agent debate on {row2.get('Name',pick2)} ({pick2}). "
                      f"Data: {row2}. BTC=${bpx}, ETH=${epx}. "
                      f"BULL WHALE | BEAR TRADER | QUANT | RISK MGR. FINAL CONSENSUS required.")
                with st.spinner('Debating…'):
                    try: st.markdown(client.generate_content(p2).text)
                    except Exception as ex: st.error(f'AI error: {ex}')
            else:
                st.info('Add GEMINI_API_KEY to Streamlit secrets.')
                cols=st.columns(3)
                [cols[i%3].metric(k,v) for i,(k,v) in enumerate(row2.items())]
else:
    st.info('Scanner Ready. Set Scan Depth and click **EXECUTE FULL CRYPTO AUDIT**.')
    st.markdown('''---
### 🪙 Crypto Sniper Elite v1.0 — CryptoCompare Edition
Nifty Sniper v16.0 logic rebuilt for the top 500 crypto markets.

**📡 Data source:** CryptoCompare (from public-apis list) — No auth required.
- `/top/mktcapfull` — 100 coins per call with live price, volume, 24h change
- `/v2/histoday` — 366 days daily OHLCV (open/high/low/close/volume) per coin

| Signal | Meaning |
|--------|---------|
| 🚀 STRONG BUY | Price surge + volume — institutional entry NOW |
| 🔴 STRONG SELL | Dump + volume — distribution phase |
| 🔄 REVERSION BUY | Z-Score < -2.2 — snap-back imminent |
| ✅ ACCUMULATE | Above MA200 + ADX>25 — confirmed uptrend |
| 🟡 NEUTRAL | No clear directional edge — stand aside |
''')
