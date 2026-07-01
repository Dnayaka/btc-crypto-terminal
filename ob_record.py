#!/usr/bin/env python3
# ob_record.py — RECORDER order book: poll depth Binance tiap jalan, akumulasi resting-liquidity
# per harga dgn DECAY (window ~beberapa jam). Snapshot Binance cuma ±0.2%, tapi pas harga gerak,
# akumulasi melebar -> peta "di mana likuiditas order sering nongkrong" (bid=beli/support, ask=jual/resist).
# Pola sama liq_real/ai_gen: cron tulis file, server publik (NOL key) cuma BACA. Jalur fetch = bget (direct->proxy).
import json, os, time, tempfile
import requests, urllib3; urllib3.disable_warnings()
HERE=os.path.dirname(os.path.abspath(__file__))
STATE=os.path.join(HERE,"ob_state.json"); OUT=os.path.join(HERE,"ob_liq.json")
SYMS={"BTCUSDT":"BTCUSDT","ETHUSDT":"ETHUSDT","SOLUSDT":"SOLUSDT"}
FAPI="https://fapi.binance.com"
DECAY=0.985   # per-run; cron */2min -> ~½ umur 1.5jam, fade lama otomatis
S=requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0"})

def fetch(path):
    for u in (FAPI+path, "https://proxy.cors.sh/"+FAPI+path):
        try:
            r=S.get(u,timeout=8,verify=False); j=r.json()
            if isinstance(j,dict) and "bids" in j and j["bids"]: return j
        except Exception: pass
    return None

def nice_step(mid):
    return 20.0 if mid>=10000 else (2.0 if mid>=1000 else (0.1 if mid>=10 else 0.01))

def load(p):
    try: return json.load(open(p))
    except Exception: return {}

def main():
    state=load(STATE); now=int(time.time()); out={}
    for ui,bs in SYMS.items():
        d=fetch(f"/fapi/v1/depth?symbol={bs}&limit=1000")
        if not d: print(f"{ui}: fetch gagal"); continue
        try:
            bids=[(float(p),float(q)) for p,q in d["bids"]]; asks=[(float(p),float(q)) for p,q in d["asks"]]
            mid=(bids[0][0]+asks[0][0])/2; step=nice_step(mid)
        except Exception as e: print(f"{ui}: parse err {e}"); continue
        s=state.get(ui) or {}
        if s.get("step")!=step: s={"bid":{},"ask":{},"step":step}
        bid=s.get("bid",{}); ask=s.get("ask",{})
        for m in (bid,ask):                                  # decay + buang remah
            for k in list(m.keys()):
                m[k]*=DECAY
                if m[k]<0.02: del m[k]
        for p,q in bids: k=str(int(round(p/step))); bid[k]=bid.get(k,0)+q
        for p,q in asks: k=str(int(round(p/step))); ask[k]=ask.get(k,0)+q
        state[ui]={"bid":bid,"ask":ask,"step":step,"mid":mid,"updated":now}
        # bangun output bins (gabung, normalisasi)
        bins=[{"price":round(int(k)*step,2),"side":"bid","v":v} for k,v in bid.items()]+\
             [{"price":round(int(k)*step,2),"side":"ask","v":v} for k,v in ask.items()]
        mx=max((b["v"] for b in bins),default=1) or 1
        bins=[{"price":b["price"],"side":b["side"],"v":round(b["v"]/mx,4)} for b in bins if b["v"]/mx>=0.05]
        bins=sorted(bins,key=lambda b:-b["v"])[:160]
        bt=round(sum(v for v in bid.values())); at=round(sum(v for v in ask.values()))
        out[ui]={"mid":round(mid,2),"binw":step,"bins":bins,"bid_total":bt,"ask_total":at,
                 "samples":s.get("samples",0)+1,"updated":now}
        state[ui]["samples"]=out[ui]["samples"]
        print(f"{ui}: {len(bins)} bins | mid {mid:.1f} | bid {bt} ask {at} | sample#{out[ui]['samples']}")
    for path,obj in ((STATE,state),(OUT,out)):
        if obj:
            fd,tmp=tempfile.mkstemp(dir=HERE,suffix=".tmp")
            with os.fdopen(fd,"w") as f: json.dump(obj,f)
            os.replace(tmp,path)
    if out: print("wrote",OUT)

if __name__=="__main__": main()
