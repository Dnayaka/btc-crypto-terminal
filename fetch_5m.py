#!/usr/bin/env python3
"""Fetch full 5m BTCUSDT.P history -> btc_5m_full.csv (paginasi startTime, resume-safe)."""
import os, sys, time, csv
import bot_v20_funding as B
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"btc_5m_full.csv")
START=1567962300000   # 2019-09-08 17:45 UTC (samain 15m)
BARMS=5*60*1000
rows=[]
# resume kalau file ada
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
        kl=B.bget(f"/fapi/v1/klines?symbol=BTCUSDT&interval=5m&startTime={t}&limit=1500")
    except Exception as e:
        print("gagal",str(e)[:60],"- retry 5s"); time.sleep(5); continue
    if not kl: break
    for k in kl:
        rows.append([k[0],k[1],k[2],k[3],k[4],k[5]])  # open_time,o,h,l,c,vol
    t=kl[-1][0]+BARMS; req+=1
    if req%20==0:
        print(f"  {len(rows)} bar, t={time.strftime('%Y-%m-%d',time.gmtime(t/1000))}")
        # checkpoint
        with open(OUT,"w",newline="") as f:
            w=csv.writer(f); w.writerow(["open_time","open","high","low","close","volume"]); w.writerows(rows)
    time.sleep(0.15)
with open(OUT,"w",newline="") as f:
    w=csv.writer(f); w.writerow(["open_time","open","high","low","close","volume"]); w.writerows(rows)
print(f"DONE {len(rows)} bar -> {OUT}")
