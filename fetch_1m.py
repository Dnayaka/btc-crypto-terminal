#!/usr/bin/env python3
"""Fetch full 1m BTCUSDT.P -> btc_1m_full.csv. Append-incremental (ga rewrite file gede), resume-safe."""
import os, time, csv
import bot_v20_funding as B
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"btc_1m_full.csv")
START=1672531200000; BARMS=60*1000  # 2023-01-01 UTC (recent focus, $200 scalp koheren)
# resume: baca open_time terakhir kalau file ada
t=START; have=0
if os.path.exists(OUT):
    last=None
    with open(OUT) as f:
        r=csv.reader(f); next(r,None)
        for x in r: last=x; have+=1
    if last: t=int(last[0])+BARMS
    print(f"resume: {have} bar, start {time.strftime('%Y-%m-%d',time.gmtime(t/1000))}")
else:
    with open(OUT,"w",newline="") as f:
        csv.writer(f).writerow(["open_time","open","high","low","close","volume"])
now=B.bget("/fapi/v1/time")["serverTime"]; req=0
f=open(OUT,"a",newline=""); w=csv.writer(f)
while t<now:
    try:
        kl=B.bget(f"/fapi/v1/klines?symbol=BTCUSDT&interval=1m&startTime={t}&limit=1500")
    except Exception as e:
        print("gagal",str(e)[:50],"retry 5s"); time.sleep(5); continue
    if not kl: break
    for k in kl: w.writerow([k[0],k[1],k[2],k[3],k[4],k[5]]); have+=1
    t=kl[-1][0]+BARMS; req+=1
    if req%50==0:
        f.flush(); print(f"  {have} bar, t={time.strftime('%Y-%m-%d',time.gmtime(t/1000))}")
    time.sleep(0.12)
f.close()
print(f"DONE {have} bar -> {OUT}")
