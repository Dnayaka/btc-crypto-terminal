#!/usr/bin/env python3
"""Fetch full 15m history utk symbol apapun -> {sym}_15m_full.csv (paginasi startTime, resume-safe).
Pola sama fetch_5m.py, generalized. Usage: python3 fetch_hist.py ETHUSDT [start_ms]"""
import os, sys, time, csv
import bot_v20_funding as B
HERE=os.path.dirname(os.path.abspath(__file__))
SYM=sys.argv[1] if len(sys.argv)>1 else "ETHUSDT"
OUT=os.path.join(HERE,f"{SYM[:3].lower()}_15m_full.csv")
START=int(sys.argv[2]) if len(sys.argv)>2 else 1567962300000
BARMS=15*60*1000
rows=[]
if os.path.exists(OUT):
    with open(OUT) as f:
        r=csv.reader(f); next(r,None)
        for x in r: rows.append(x)
    if rows: START=int(rows[-1][0])+BARMS
    print(f"resume dari {len(rows)} bar, start={START}")
now=B.bget("/fapi/v1/time")["serverTime"]
t=START; req=0
while t<now:
    try:
        kl=B.bget(f"/fapi/v1/klines?symbol={SYM}&interval=15m&startTime={t}&limit=1500")
    except Exception as e:
        print("gagal",str(e)[:60],"- retry 5s"); time.sleep(5); continue
    if not kl: break
    for k in kl:
        rows.append([k[0],k[1],k[2],k[3],k[4],k[5]])
    t=kl[-1][0]+BARMS; req+=1
    if req%20==0:
        print(f"  {len(rows)} bar, t={time.strftime('%Y-%m-%d',time.gmtime(t/1000))}")
        with open(OUT,"w",newline="") as f:
            w=csv.writer(f); w.writerow(["open_time","open","high","low","close","volume"]); w.writerows(rows)
    if len(kl)<1500: break
with open(OUT,"w",newline="") as f:
    w=csv.writer(f); w.writerow(["open_time","open","high","low","close","volume"]); w.writerows(rows)
print(f"DONE {SYM}: {len(rows)} bar -> {OUT}")
