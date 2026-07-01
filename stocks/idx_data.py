#!/usr/bin/env python3
"""idx_data.py — tarik IDX GetStockSummary (PROTON OFF / IP residensial). 1 request = SEMUA saham:
OHLCV + nilai + NET FOREIGN FLOW (asing beli/jual) + bid/offer. = bandarmology REAL (asing=smart-money).
Plus GetBrokerSummary (top broker market-wide). Simpan idx_summary.json. curl_cffi impersonate.

  python3 idx_data.py            # fetch + simpan
"""
import json, os, time, datetime
from curl_cffi import requests
HERE=os.path.dirname(os.path.abspath(__file__))
B="https://www.idx.co.id/primary/TradingSummary/"
HOME="https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-broker/"

def sess():
    s=requests.Session(impersonate="chrome120")
    s.get(HOME, timeout=20)
    s.headers.update({"Accept":"application/json, text/plain, */*","Referer":HOME})
    return s

def last_trading_dates(n=6):
    """list tanggal mundur dari hari ini (skip weekend) utk cari hari-bursa terakhir."""
    out=[]; d=datetime.date.today()
    while len(out)<n:
        if d.weekday()<5: out.append(d.strftime("%Y%m%d"))
        d-=datetime.timedelta(days=1)
    return out

def fetch_stock_summary(s, date=None):
    dates=[date] if date else last_trading_dates()
    for dt in dates:
        r=s.get(B+"GetStockSummary", params={"date":dt,"start":0,"length":1200}, timeout=25)
        data=r.json().get("data",[])
        if data: return data
    return []

def fetch_top_brokers(s, date=None, n=15):
    dt=(last_trading_dates(1)[0] if not date else date)
    r=s.get(B+"GetBrokerSummary", params={"date":dt,"start":0,"length":150}, timeout=20)
    d=r.json().get("data",[])
    if not d:
        for dt in last_trading_dates():
            r=s.get(B+"GetBrokerSummary", params={"date":dt,"start":0,"length":150}, timeout=20)
            d=r.json().get("data",[])
            if d: break
    d=sorted(d, key=lambda x:-(x.get("Value") or 0))[:n]
    return [{"code":x.get("IDFirm"),"name":x.get("FirmName"),"val_b":round((x.get("Value") or 0)/1e9,1),
             "freq":int(x.get("Frequency") or 0)} for x in d]

def build():
    s=sess()
    rows=fetch_stock_summary(s)
    if not rows: return {"_ok":False,"_msg":"data kosong (libur/jam off?)"}
    by={}
    for r in rows:
        c=r.get("StockCode")
        if not c: continue
        fb=float(r.get("ForeignBuy") or 0); fs=float(r.get("ForeignSell") or 0); cl=float(r.get("Close") or 0)
        by[c]=dict(close=cl, change=float(r.get("Change") or 0), volume=float(r.get("Volume") or 0),
                   value=float(r.get("Value") or 0), high=float(r.get("High") or 0), low=float(r.get("Low") or 0),
                   foreign_buy=fb, foreign_sell=fs, foreign_net=round((fb-fs)*cl/1e9,2),  # net asing (Rp miliar approx)
                   foreign_net_lot=int(fb-fs),
                   freq=int(r.get("Frequency") or 0))
    date=rows[0].get("Date","")[:10]
    top=fetch_top_brokers(s, n=15)
    # agregat FOREIGN FLOW (asing) = bandarmology REAL
    liq=[(c,st["foreign_net"]) for c,st in by.items() if st.get("value",0)>2e9]   # likuid: nilai>Rp2M
    liq.sort(key=lambda x:-x[1])
    top_fbuy=[{"code":c,"net":n} for c,n in liq[:12] if n>0]
    top_fsell=[{"code":c,"net":n} for c,n in liq[::-1][:12] if n<0]
    mkt_fnet=round(sum(st["foreign_net"] for st in by.values()),0)
    out={"_ok":True,"_ts":int(time.time()),"_date":date,"n":len(by),"stocks":by,"top_brokers":top,
         "market_foreign_net":mkt_fnet,"top_fbuy":top_fbuy,"top_fsell":top_fsell}
    json.dump(out, open(os.path.join(HERE,"idx_summary.json"),"w"), indent=1)
    return out

if __name__=="__main__":
    o=build()
    if not o.get("_ok"): print("GAGAL:",o.get("_msg")); raise SystemExit
    print(f"IDX summary {o['_date']} | {o['n']} saham -> idx_summary.json")
    print("\nNET FOREIGN FLOW watchlist (Rp miliar, + = asing beli / - = asing jual):")
    for c in ["BBCA","BBRI","GGRM","MAPI","TINS","ADRO","MEDC","PTBA","ANTM","GOTO","TLKM","UNVR"]:
        st=o["stocks"].get(c)
        if st: print(f"  {c:6s} close {st['close']:>8.0f}  asing-net {st['foreign_net']:>+8.1f} M  vol-val {st['value']/1e9:>7.1f} M")
    print("\nTOP BROKER market-wide hari ini:")
    for b in o["top_brokers"][:8]: print(f"  {b['code']:3s} {b['name'][:28]:28s} {b['val_b']:>8.1f} M  {b['freq']} freq")
