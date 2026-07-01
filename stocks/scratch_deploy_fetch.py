#!/usr/bin/env python3
"""scratch_deploy_fetch.py — DEPLOY lens fetcher (ADDITIVE only).
Tambah ~25-35 saham IDX likuid (LQ45-ext / IDX80 mid-cap) meniru pola fetch_stocks.py.
- Proxy: cors.sh dulu (allorigins lagi 522), fallback allorigins.
- TIDAK menimpa file CSV yang sudah ada; TIDAK menyentuh _manifest.json.
- Skip simbol yang gagal / data < min_bars.
"""
import os, sys, time, json
sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
from urllib.parse import quote
import pandas as pd
import requests, urllib3
urllib3.disable_warnings()

HERE = "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks"
DATA = os.path.join(HERE, "data")
SINCE = "2020-01-01"
MIN_BARS = 300  # samakan dgn pf.load_data min_bars

_S = requests.Session()
_S.headers.update({"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"})
VERIFY = False

# kandidat DEPLOY (skip AKRA/INKP — sudah ada di data/)
NEW = ["BBTN","BNGA","MEGA","PNBN","BJBR","BJTM","MAPA","ERAA","RALS","LPPF",
       "SCMA","MNCN","TBIG","WTON","PTPP","ADHI","SMRA","SSMS","LSIP","AALI",
       "DSNG","TINS","NCKL","ESSA","PGEO","ELSA","KKGI","HRUM"]
NEW = [s+".JK" for s in NEW]

def _via_corssh(target):
    r=_S.get("https://proxy.cors.sh/"+target, timeout=45, verify=VERIFY)
    if r.status_code!=200: return None,f"cors.sh HTTP {r.status_code}"
    return r.text,None
def _via_allorigins(target):
    r=_S.get("https://api.allorigins.win/get?url="+quote(target,safe=""), timeout=45, verify=VERIFY)
    if r.status_code!=200: return None,f"allorigins HTTP {r.status_code}"
    try: return json.loads(r.text).get("contents",""),None
    except Exception as e: return None,f"allorigins wrap {str(e)[:40]}"
PROXIES=[("cors.sh",_via_corssh),("allorigins",_via_allorigins)]

def _parse(text):
    j=json.loads(text); res=j["chart"]["result"]
    if not res: raise ValueError("no result")
    R=res[0]; ts=R.get("timestamp") or []
    if not ts: raise ValueError("0 bar")
    q=R["indicators"]["quote"][0]
    adj=(R["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
    df=pd.DataFrame({"ts":ts,"open":q["open"],"high":q["high"],"low":q["low"],
                     "close":q["close"],"adjclose":adj,"volume":q["volume"]})
    df=df.dropna(subset=["open","high","low","close"]).reset_index(drop=True)
    df["dt"]=pd.to_datetime(df["ts"],unit="s",utc=True).dt.tz_convert("Asia/Jakarta").dt.tz_localize(None)
    return df[["dt","open","high","low","close","adjclose","volume"]]

def fetch_daily(sym, since=SINCE, tries=4, pause=1.5):
    p1=int(pd.Timestamp(since).timestamp()); p2=int(time.time())
    s=quote(sym,safe=""); url=f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={p1}&period2={p2}&interval=1d"
    last="?"
    for attempt in range(tries):
        for pname,pf_ in PROXIES:
            try:
                txt,err=pf_(url)
                if err: last=err; continue
                return _parse(txt), pname
            except Exception as e:
                last=f"{pname}:{str(e)[:40]}"
        time.sleep(pause*(attempt+1))
    return None, f"GAGAL({last})"

def path_of(sym): return os.path.join(DATA, sym+".csv")

def run():
    man={}; ok=0; t0=time.time()
    for i,sym in enumerate(NEW,1):
        p=path_of(sym)
        if os.path.exists(p):
            print(f"[{i}/{len(NEW)}] {sym:10s} SKIP (sudah ada)");
            man[sym]={"status":"exists"}; continue
        df,info=fetch_daily(sym)
        if df is not None and len(df)>=MIN_BARS:
            df.to_csv(p, index=False); ok+=1
            man[sym]={"rows":len(df),"start":str(df['dt'].iloc[0].date()),"end":str(df['dt'].iloc[-1].date()),"via":info,"status":"ok"}
            print(f"[{i}/{len(NEW)}] {sym:10s} OK {len(df)} bar {df['dt'].iloc[0].date()}->{df['dt'].iloc[-1].date()} via {info}", flush=True)
        else:
            man[sym]={"status":"FAIL","info":info,"rows":(len(df) if df is not None else 0)}
            print(f"[{i}/{len(NEW)}] {sym:10s} {info} (rows={len(df) if df is not None else 0})", flush=True)
        time.sleep(1.6)
    json.dump(man, open(os.path.join(DATA,"_manifest_deploy.json"),"w"), indent=1)
    print(f"\nSELESAI fetch baru {ok}/{len(NEW)} dalam {time.time()-t0:.0f}s")

if __name__=="__main__":
    run()
