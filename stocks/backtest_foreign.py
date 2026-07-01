#!/usr/bin/env python3
"""backtest_foreign.py — apakah NET FOREIGN FLOW prediksi return ke depan?
foreign_hist.json {date:{code:[close,fnet]}}. Tiap hari rank fnet -> top-buy vs top-sell ->
forward H-day return. Cek monoton + WR. Naikin WR mean-reversion?"""
import json, os, numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
H=json.load(open(os.path.join(HERE,"foreign_hist.json")))
dates=sorted(H)
# panel per stock
close={}; fnet={}
for dt in dates:
    for c,(cl,fn) in H[dt].items():
        close.setdefault(c,{})[dt]=cl; fnet.setdefault(c,{})[dt]=fn

def fwd_ret(c, di, h):
    if di+h>=len(dates): return None
    d0,d1=dates[di],dates[di+h]
    if d0 in close[c] and d1 in close[c] and close[c][d0]>0:
        return close[c][d1]/close[c][d0]-1
    return None

print(f"{len(dates)} hari, {len(close)} saham\n")
print("=== FOREIGN-FLOW -> FORWARD RETURN (top/bottom K=15 by net-asing Rp) ===")
print(f"{'H':>3} | {'topBUY ret':>10} {'WR':>5} | {'topSELL ret':>11} {'WR':>5} | {'SPREAD':>7} | {'allWR':>5}")
for h in [1,3,5,10,20]:
    tb=[]; ts=[]; allr=[]
    for di in range(len(dates)-h):
        dt=dates[di]
        rows=[(c,v[1]) for c,v in [(c,H[dt][c]) for c in H[dt]] if True]  # (code,fnet)
        rows=[(c,fn) for c,fn in rows if fwd_ret(c,di,h) is not None]
        if len(rows)<40: continue
        rows.sort(key=lambda x:-x[1])
        K=15
        for c,_ in rows[:K]:
            r=fwd_ret(c,di,h); tb.append(r)
        for c,_ in rows[-K:]:
            r=fwd_ret(c,di,h); ts.append(r)
        for c,_ in rows: allr.append(fwd_ret(c,di,h))
    tb=np.array(tb); ts=np.array(ts); allr=np.array(allr)
    print(f"{h:>3} | {tb.mean()*100:>+9.2f}% {(tb>0).mean()*100:>4.0f}% | {ts.mean()*100:>+10.2f}% {(ts>0).mean()*100:>4.0f}% | {(tb.mean()-ts.mean())*100:>+6.2f}% | {(allr>0).mean()*100:>4.0f}%")

print("\n=== QUINTILE (H=5): split rank fnet jadi 5 grup, mean forward-ret ===")
h=5; groups=[[] for _ in range(5)]
for di in range(len(dates)-h):
    dt=dates[di]
    rows=[(c,H[dt][c][1]) for c in H[dt] if fwd_ret(c,di,h) is not None]
    if len(rows)<50: continue
    rows.sort(key=lambda x:x[1])  # asc: jual->beli
    n=len(rows)
    for gi in range(5):
        for c,_ in rows[gi*n//5:(gi+1)*n//5]:
            groups[gi].append(fwd_ret(c,di,h))
for gi,g in enumerate(groups):
    g=np.array(g); lab=['Q1 jual-terberat','Q2','Q3 netral','Q4','Q5 beli-terberat'][gi]
    print(f"  {lab:18s}: ret {g.mean()*100:>+.2f}%  WR {(g>0).mean()*100:.0f}%  n={len(g)}")
