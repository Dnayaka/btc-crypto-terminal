#!/usr/bin/env python3
"""fetch_stocks.py — bulk download OHLCV harian saham IDX + IHSG via Yahoo chart API
LEWAT proxy server-side (akali blokir IP ProtonVPN). Resumable, fallback proxy, polite.

Universe = LQ45/IDX30 mid-large cap (likuid, berkualitas) = "filter fundamental" bersih.
Output: stocks/data/{SYM}.csv  + stocks/data/_manifest.json

  python3 fetch_stocks.py            # download semua yg belum ada
  python3 fetch_stocks.py --force    # re-download semua
  python3 fetch_stocks.py --update   # refresh bar terakhir (incremental, dipakai cron)
"""
import os, sys, time, json
from urllib.parse import quote
import pandas as pd, numpy as np
import requests, urllib3
urllib3.disable_warnings()

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)
SINCE = "2020-01-01"

_S = requests.Session()
_S.headers.update({"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"})
VERIFY = False

# IHSG index + ~40 saham likuid LQ45/IDX30 (bank, telco, konsumer, energi/tambang, properti, tech)
INDEX = "^JKSE"
UNIVERSE = [
    # Bank
    "BBCA.JK","BBRI.JK","BMRI.JK","BBNI.JK","BRIS.JK","BTPS.JK","ARTO.JK",
    # Telco / tower
    "TLKM.JK","EXCL.JK","ISAT.JK","TOWR.JK","MTEL.JK",
    # Konsumer / ritel / farmasi
    "UNVR.JK","ICBP.JK","INDF.JK","MYOR.JK","KLBF.JK","SIDO.JK","CPIN.JK","AMRT.JK","MAPI.JK","ACES.JK","HMSP.JK","GGRM.JK",
    # Energi / tambang / kimia
    "ASII.JK","UNTR.JK","ANTM.JK","ADRO.JK","PTBA.JK","ITMG.JK","INCO.JK","MDKA.JK","PGAS.JK","AKRA.JK","INKP.JK","TPIA.JK","MEDC.JK","AMMN.JK","BRPT.JK",
    # Properti / infra / semen
    "BSDE.JK","CTRA.JK","PWON.JK","SMGR.JK","INTP.JK","JSMR.JK",
    # Tech / new economy
    "GOTO.JK","BUKA.JK","EMTK.JK",
]

def _via_allorigins(target):
    r=_S.get("https://api.allorigins.win/get?url="+quote(target,safe=""), timeout=45, verify=VERIFY)
    if r.status_code!=200: return None,f"allorigins HTTP {r.status_code}"
    try: return json.loads(r.text).get("contents",""),None
    except Exception as e: return None,f"allorigins wrap {str(e)[:40]}"

def _via_corssh(target):
    r=_S.get("https://proxy.cors.sh/"+target, timeout=45, verify=VERIFY)
    if r.status_code!=200: return None,f"cors.sh HTTP {r.status_code}"
    return r.text,None

PROXIES=[("allorigins",_via_allorigins),("cors.sh",_via_corssh)]

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

def fetch_daily(sym, since=SINCE, to=None, tries=4, pause=1.5):
    p1=int(pd.Timestamp(since).timestamp()); p2=int(pd.Timestamp(to).timestamp()) if to else int(time.time())
    s=quote(sym,safe=""); url=f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={p1}&period2={p2}&interval=1d"
    last="?"
    for attempt in range(tries):
        for pname,pf in PROXIES:
            try:
                txt,err=pf(url)
                if err: last=err; continue
                return _parse(txt), f"{pname}"
            except Exception as e:
                last=f"{pname}:{str(e)[:40]}"
        time.sleep(pause*(attempt+1))
    return None, f"GAGAL({last})"

def path_of(sym): return os.path.join(DATA, sym.replace("^","_")+".csv")

def run(force=False, update=False):
    syms=[INDEX]+UNIVERSE
    manifest={}; ok=0; t0=time.time()
    for i,sym in enumerate(syms,1):
        p=path_of(sym)
        if os.path.exists(p) and not force and not update:
            try:
                d=pd.read_csv(p); manifest[sym]={"rows":len(d),"status":"cached"}; ok+=1
                print(f"[{i}/{len(syms)}] {sym:10s} cached ({len(d)} bar)"); continue
            except Exception: pass
        df,info=fetch_daily(sym)
        if df is not None and len(df)>50:
            df.to_csv(p, index=False)
            manifest[sym]={"rows":len(df),"start":str(df['dt'].iloc[0].date()),"end":str(df['dt'].iloc[-1].date()),"via":info,"status":"ok"}
            ok+=1
            print(f"[{i}/{len(syms)}] {sym:10s} OK {len(df)} bar {df['dt'].iloc[0].date()}->{df['dt'].iloc[-1].date()} via {info}", flush=True)
        else:
            manifest[sym]={"status":"FAIL","info":info}
            print(f"[{i}/{len(syms)}] {sym:10s} {info}", flush=True)
        time.sleep(1.6)
    manifest["_meta"]={"ok":ok,"total":len(syms),"secs":round(time.time()-t0),"ts":int(time.time())}
    json.dump(manifest, open(os.path.join(DATA,"_manifest.json"),"w"), indent=1)
    print(f"\nSELESAI {ok}/{len(syms)} dalam {time.time()-t0:.0f}s -> {DATA}")

if __name__=="__main__":
    run(force="--force" in sys.argv, update="--update" in sys.argv)
