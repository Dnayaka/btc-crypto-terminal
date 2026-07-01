#!/usr/bin/env python3
"""idx_foreign_hist.py — tarik HISTORY foreign-flow IDX (loop GetStockSummary per tanggal, Proton OFF).
Buat backtest: apakah net-asing prediksi return ke depan. Resumable, compact (likuid saja).
Output foreign_hist.json = {date: {code: [close, foreign_net_value_Rp]}}.

  python3 idx_foreign_hist.py 240     # 240 hari-bursa terakhir
"""
import json, os, sys, time, datetime
from curl_cffi import requests
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"foreign_hist.json")
B="https://www.idx.co.id/primary/TradingSummary/GetStockSummary"
HOME="https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-broker/"

def sess():
    s=requests.Session(impersonate="chrome120"); s.get(HOME,timeout=20)
    s.headers.update({"Accept":"application/json, text/plain, */*","Referer":HOME}); return s

def trading_days(n):
    out=[]; d=datetime.date.today()
    while len(out)<n:
        if d.weekday()<5: out.append(d.strftime("%Y%m%d"))
        d-=datetime.timedelta(days=1)
    return out

def main():
    n=int(sys.argv[1]) if len(sys.argv)>1 else 220
    hist={}
    if os.path.exists(OUT):
        try: hist=json.load(open(OUT))
        except Exception: pass
    s=sess(); days=trading_days(n); got=0; t0=time.time()
    for i,dt in enumerate(days):
        key=dt[:4]+"-"+dt[4:6]+"-"+dt[6:]
        if key in hist: continue
        try:
            r=s.get(B,params={"date":dt,"start":0,"length":1200},timeout=22); d=r.json().get("data",[])
        except Exception as e:
            print(f"  {dt} ERR {str(e)[:40]}"); time.sleep(1); continue
        if not d: continue   # libur
        row={}
        for x in d:
            c=x.get("StockCode"); cl=float(x.get("Close") or 0); val=float(x.get("Value") or 0)
            if not c or cl<=0 or val<1e9: continue   # likuid saja (nilai>Rp1M)
            fnet=(float(x.get("ForeignBuy") or 0)-float(x.get("ForeignSell") or 0))*cl
            row[c]=[round(cl,2), round(fnet/1e9,3)]   # close, foreign-net Rp miliar
        hist[key]=row; got+=1
        if got%10==0:
            json.dump(hist,open(OUT,"w")); print(f"  {got} hari ({key}, {len(row)} saham) {time.time()-t0:.0f}s",flush=True)
        time.sleep(0.5)
    json.dump(hist,open(OUT,"w"))
    ds=sorted(hist); print(f"SELESAI: {len(hist)} hari ({ds[0]}..{ds[-1]}) -> foreign_hist.json")

if __name__=="__main__": main()
