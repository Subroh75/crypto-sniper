#!/usr/bin/env python3
"""Crypto Sniper E2E Health Suite - alirezarezvani/claude-skills methodology"""
import urllib.request, urllib.error, json, sys, time, ssl, socket, base64, threading
BASE = "https://crypto-sniper.onrender.com"
FRONTEND = "https://crypto-sniper.app"
RESULTS = []
def log(msg): print(msg, flush=True)
def api(path, method="GET", body=None, base=BASE):
    url = base + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type":"application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as r: return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e: return {"error":e.reason,"status":e.code}, e.code
    except Exception as e: raise RuntimeError(f"Request failed: {e}")
def record(name, passed, detail, fix=""):
    RESULTS.append({"name":name,"passed":passed,"detail":detail,"fix":fix})
    log(f"{'[PASS]' if passed else '[FAIL]'} {name}: {detail}")
    if not passed and fix: log(f"      FIX -> {fix}")
def test_t1_price():
    j,_ = api("/analyse","POST",{"symbol":"BTC","interval":"1h"})
    p = j.get("quote",{}).get("price",0)
    record("T1 BTC live price", p>1000, f"price={p:.2f}", "Check _binance_quote() in data.py")
def test_t2_fear_greed():
    j,_ = api("/analyse","POST",{"symbol":"BTC","interval":"1h"})
    v = j.get("fear_greed",{}).get("value",-1)
    record("T2 Fear and Greed", 0<=v<=100, f"value={v}", "Wire get_fear_greed() into api.py")
def test_t3_ohlcv():
    j,_ = api("/analyse","POST",{"symbol":"BTC","interval":"1h"})
    ohlcv = j.get("ohlcv",[])
    prices = [c[4] for c in ohlcv] if ohlcv else []
    lo,hi = (min(prices),max(prices)) if prices else (0,0)
    ok = len(ohlcv)>=48 and (len(ohlcv[0])==5 if ohlcv else False) and (hi-lo)>100
    record("T3 OHLCV quality", ok, f"count={len(ohlcv)} range={lo:.0f}-{hi:.0f}", "Check _binance_ohlcv()")
def test_t4_s_score():
    j,_ = api("/analyse","POST",{"symbol":"BTC","interval":"1h"})
    s = j.get("components",{}).get("S",{}).get("score",-1)
    fg = j.get("fear_greed",{}).get("value",50)
    record("T4 S score", s>=0 and (s>0 or 30<=fg<=70), f"S={s}/3 F&G={fg}", "signals.py not receiving fear_greed")
def test_t5_scan():
    j,st = api("/scan?interval=1h&min_score=5")
    record("T5 /scan endpoint", st==200 and isinstance(j.get("signals"),list), f"status={st}", "backend/main.py add interval.lower()")
def test_t6_kronos():
    j,_ = api("/kronos","POST",{"symbol":"BTC","interval":"1h","context":"test"})
    c = j.get("forecast",{}).get("predicted_ohlcv",[])
    ok = len(c)==24 and (all(k in c[0] for k in ["open","high","low","close"]) if c else False) and (c[0].get("close",0)>1000 if c else False)
    record("T6 Kronos forecast", ok, f"candles={len(c)}", "Kronos price anchor=0")
def test_t7_market():
    j,_ = api("/market")
    cap = j.get("total_market_cap_usd",0)
    record("T7 Market bar", cap>1e12 and 0<j.get("btc_dominance",0)<100, f"cap={cap/1e12:.2f}T", "get_market_overview() dead endpoint")
def test_t8_keys():
    j,_ = api("/health")
    srcs = j.get("sources",{})
    no_key = [k for k,v in srcs.items() if v=="no_key"]
    record("T8 API keys", len(no_key)==0, f"no_key={no_key}", "Set keys in Render env vars")
def test_t9_frontend():
    try:
        with urllib.request.urlopen(urllib.request.Request(FRONTEND),timeout=30) as r:
            record("T9 Frontend", r.status==200, f"status={r.status}")
    except Exception as e: record("T9 Frontend", False, str(e)[:80])
def test_t10_ws():
    received = []
    def chk():
        try:
            ctx = ssl.create_default_context()
            s = socket.create_connection(("stream.binance.com",9443),timeout=10)
            ss = ctx.wrap_socket(s,server_hostname="stream.binance.com")
            key = base64.b64encode(b"cryptosniperhealthcheck1").decode()
            hs = f"GET /stream?streams=btcusdt@miniTicker HTTP/1.1\r\nHost: stream.binance.com:9443\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ss.send(hs.encode())
            resp = ss.recv(1024).decode("utf-8","ignore")
            if "101" in resp:
                d = ss.recv(4096)
                if len(d)>10: received.append(len(d))
            ss.close()
        except: pass
    t=threading.Thread(target=chk); t.start(); t.join(timeout=15)
    record("T10 Binance WS", len(received)>0, f"bytes={received[0] if received else 0}", "Check useLivePrices() in useApi.ts")
def main():
    log("="*60); log("CRYPTO SNIPER E2E HEALTH CHECK"); log(f"Target: {BASE}"); log("="*60)
    log("Warming Render backend...")
    try: api("/health")
    except: pass
    time.sleep(3)
    for fn in [test_t1_price,test_t2_fear_greed,test_t3_ohlcv,test_t4_s_score,test_t5_scan,test_t6_kronos,test_t7_market,test_t8_keys,test_t9_frontend,test_t10_ws]:
        log(""); 
        try: fn()
        except Exception as e: record(fn.__name__,False,f"Crashed: {e}")
    passed = sum(1 for r in RESULTS if r["passed"]); total = len(RESULTS)
    log(""); log("="*60); log(f"SCORE: {passed}/{total} ({int(passed/total*100) if total else 0}%)"); log("="*60)
    failed = [r for r in RESULTS if not r["passed"]]
    if failed:
        log("\nACTION ITEMS:")
        for i,r in enumerate(failed,1):
            log(f"  {i}. {r['name']}")
            if r["fix"]: log(f"     -> {r['fix']}")
    return 0 if passed==total else 1
if __name__=="__main__": sys.exit(main())
