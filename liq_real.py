#!/usr/bin/env python3
# liq_real.py — bangun heatmap LIKUIDASI NYATA per-harga (30 hari) dari Coinalyze.
# Sumber NYATA: /liquidation-history (long/short USD per jam) + /ohlcv-history (range harga per jam).
# Tiap jam, liq dibagi rata ke bin harga yang dilewati candle jam itu -> "di mana liq beneran terjadi".
# Output liq_real.json dibaca config_server.py /api/liqmap (server publik NOL key — pola sama ai_gen).
import json, os, time, urllib.request, urllib.parse, tempfile
HERE=os.path.dirname(os.path.abspath(__file__))
KEYF=os.path.expanduser("~/.coinalyze_key")
OUT=os.path.join(HERE,"liq_real.json")
SYMS={"BTCUSDT":"BTCUSDT_PERP.A","ETHUSDT":"ETHUSDT_PERP.A","SOLUSDT":"SOLUSDT_PERP.A"}
DAYS=30

def get(path,key,**p):
    url=f"https://api.coinalyze.net/v1{path}?"+urllib.parse.urlencode(p)
    req=urllib.request.Request(url, headers={"api_key":key})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req,timeout=40) as r: return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(4); continue
            return None
        except Exception: time.sleep(2)
    return None

def build(coinsym, key, now):
    frm=now-DAYS*86400
    lh=get("/liquidation-history",key,symbols=coinsym,interval="1hour",**{"from":frm,"to":now,"convert_to_usd":"true"})
    oh=get("/ohlcv-history",key,symbols=coinsym,interval="1hour",**{"from":frm,"to":now})
    if not (lh and oh and lh[0].get("history") and oh[0].get("history")): return None
    liq={(x['t']//3600)*3600:(x.get('l',0) or 0, x.get('s',0) or 0) for x in lh[0]["history"]}
    bars={(x['t']//3600)*3600:(x['h'],x['l'],x['c']) for x in oh[0]["history"]}
    hrs=sorted(set(liq)&set(bars))
    if not hrs: return None
    mid=bars[hrs[-1]][2]
    binw=mid*0.0025
    longb={}; shortb={}; lt=0.0; sttot=0.0
    for h in hrs:
        L,S=liq[h]; hi,lo,_=bars[h]; lt+=L; sttot+=S
        blo=int(round(lo/binw)); bhi=int(round(hi/binw)); nb=max(1,bhi-blo+1)
        for kb in range(blo,bhi+1):
            if L: longb[kb]=longb.get(kb,0)+L/nb
            if S: shortb[kb]=shortb.get(kb,0)+S/nb
    bins=[{"price":round(k*binw,1),"side":"long","v":v} for k,v in longb.items()]+\
         [{"price":round(k*binw,1),"side":"short","v":v} for k,v in shortb.items()]
    if not bins: return None
    mx=max(b["v"] for b in bins) or 1
    bins=[{"price":b["price"],"side":b["side"],"v":round(b["v"]/mx,4)} for b in bins if b["v"]/mx>=0.04]
    bins=sorted(bins,key=lambda b:-b["v"])[:120]
    return {"mid":round(mid,2),"binw":round(binw,2),"bins":bins,
            "long_total":round(lt),"short_total":round(sttot),"hours":len(hrs),"updated":now}

def main():
    if not os.path.exists(KEYF):
        print("no coinalyze key"); return
    key=open(KEYF).read().strip(); now=int(time.time()); out={}
    for ui,cs in SYMS.items():
        try:
            d=build(cs,key,now)
            if d: out[ui]=d; print(f"{ui}: {len(d['bins'])} bins | mid {d['mid']} | long ${d['long_total']/1e6:.0f}M short ${d['short_total']/1e6:.0f}M | {d['hours']}h")
            else: print(f"{ui}: SKIP (data kosong)")
        except Exception as e:
            print(f"{ui}: ERR {e}")
        time.sleep(0.5)
    if out:
        fd,tmp=tempfile.mkstemp(dir=HERE,suffix=".tmp");
        with os.fdopen(fd,"w") as f: json.dump(out,f)
        os.replace(tmp,OUT); print("wrote",OUT)

if __name__=="__main__": main()
