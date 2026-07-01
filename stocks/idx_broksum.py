#!/usr/bin/env python3
"""idx_broksum.py — fetch BROKER SUMMARY (kode broker AK/BK/CC net beli-jual) per saham dari
IDX hidden API, pakai cookie cf_clearance + UA dari browser user (ditaruh .idx_cookie via /admin).
Batch semua watchlist sekali jalan (hemat), cache ke broksum.json. Graceful kalau cookie kosong/expired.

  python3 idx_broksum.py            # fetch broksum utk watchlist di stocks_signal.json
  python3 idx_broksum.py --raw BBCA # dump 1 saham mentah (debug parser)
"""
import os, sys, json, time
import requests, urllib3
urllib3.disable_warnings()
HERE=os.path.dirname(os.path.abspath(__file__))
COOKIE_F=os.path.join(HERE,".idx_cookie"); OUT=os.path.join(HERE,"broksum.json"); RAW=os.path.join(HERE,".broksum_raw.json")
EP="https://www.idx.co.id/primary/TradingSummary/GetBrokerSummary"

def load_cookie():
    try:
        d=json.load(open(COOKIE_F)); return d.get("cookie",""), d.get("ua","")
    except Exception: return "",""

def session():
    """curl_cffi impersonate Chrome (TLS = browser asli) + cookie cf_clearance dari browser user.
    Replay dari IP Proton yg SAMA dgn browser -> peluang terbaik tembus Cloudflare di Proton."""
    ck,ua=load_cookie()
    try:
        from curl_cffi import requests as creq
        s=creq.Session(impersonate="chrome120")
    except Exception:
        s=requests.Session()
    s.headers.update({"Accept":"application/json, text/plain, */*",
        "Referer":"https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-broker/",
        "X-Requested-With":"XMLHttpRequest"})
    if ua: s.headers["User-Agent"]=ua
    if ck: s.headers["Cookie"]=ck
    return s, bool(ck)

def fetch_one(s, code, date):
    params={"code":code,"date":date,"start":0,"length":200}
    r=s.get(EP, params=params, timeout=20, verify=False)
    if r.status_code!=200: return None, f"HTTP {r.status_code}"
    try: return r.json(), None
    except Exception: return None, "non-JSON (cookie expired / cloudflare?)"

def parse(j):
    """IDX broksum -> top broker net beli & net jual. Fleksibel thd bentuk respons."""
    # cari list broker (umumnya j['data'] = list dict per broker dgn buy/sell value+lot)
    rows = j.get("data") if isinstance(j,dict) else (j if isinstance(j,list) else None)
    if not isinstance(rows,list) or not rows: return None
    brokers={}
    for it in rows:
        if not isinstance(it,dict): continue
        code=it.get("BrokerCode") or it.get("brokercode") or it.get("Broker") or it.get("code")
        if not code: continue
        # nilai beli/jual: coba beberapa nama field
        bv=float(it.get("BBVal") or it.get("BuyValue") or it.get("buyvalue") or it.get("NBVal") or 0 or 0)
        sv=float(it.get("SBVal") or it.get("SellValue") or it.get("sellvalue") or it.get("NSVal") or 0 or 0)
        blot=float(it.get("BBLot") or it.get("BuyVolume") or it.get("buylot") or 0 or 0)
        slot=float(it.get("SBLot") or it.get("SellVolume") or it.get("selllot") or 0 or 0)
        b=brokers.setdefault(code,{"bv":0.0,"sv":0.0,"blot":0.0,"slot":0.0})
        b["bv"]+=bv; b["sv"]+=sv; b["blot"]+=blot; b["slot"]+=slot
    if not brokers: return None
    net=[(c, v["bv"]-v["sv"], v["blot"]-v["slot"]) for c,v in brokers.items()]
    buys=sorted([x for x in net if x[1]>0], key=lambda x:-x[1])[:5]
    sells=sorted([x for x in net if x[1]<0], key=lambda x:x[1])[:5]
    fmt=lambda v: round(v/1e9,2)  # miliar
    return dict(top_buy=[{"code":c,"net_b":fmt(v),"lot":int(l)} for c,v,l in buys],
                top_sell=[{"code":c,"net_b":fmt(v),"lot":int(l)} for c,v,l in sells],
                n_broker=len(brokers))

def watchlist_syms():
    try:
        d=json.load(open(os.path.join(HERE,"stocks_signal.json")))
        return [x["sym"].replace(".JK","") for x in (d.get("buys",[])+d.get("watchlist",[]))]
    except Exception: return []

def main():
    import datetime
    if "--raw" in sys.argv:
        code=sys.argv[sys.argv.index("--raw")+1]; s,ok=session()
        if not ok: print("no cookie di .idx_cookie"); return
        j,err=fetch_one(s,code,datetime.datetime.now().strftime("%Y%m%d"))
        if j: json.dump(j,open(RAW,"w"),indent=1); print("raw ->",RAW,"| top-level:",list(j.keys()) if isinstance(j,dict) else type(j))
        else: print("gagal:",err)
        return
    s,ok=session()
    if not ok:
        json.dump({"_ok":False,"_msg":"cookie IDX belum diisi (paste di /admin)"},open(OUT,"w")); print("no cookie."); return
    syms=watchlist_syms()[:25]; date=datetime.datetime.now().strftime("%Y%m%d")
    out={"_ts":int(time.time()),"_date":date,"_ok":True,"data":{}}
    first=True; okc=0
    for c in syms:
        j,err=fetch_one(s,c,date)
        if j is None:
            if first: out["_ok"]=False; out["_msg"]=err; print("STOP:",err); break
            continue
        if first: json.dump(j,open(RAW,"w"),indent=1); first=False   # simpan raw 1 utk debug parser
        p=parse(j)
        if p: out["data"][c]=p; okc+=1
        time.sleep(1.2)
    out["n_ok"]=okc
    json.dump(out,open(OUT,"w"),indent=1)
    print(f"broksum: {okc}/{len(syms)} saham -> {OUT}" if out["_ok"] else f"GAGAL: {out.get('_msg')}")

if __name__=="__main__": main()
