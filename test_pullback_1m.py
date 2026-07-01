#!/usr/bin/env python3
"""Tes pullback di 1m (fee=0). Sweep EMA-trend / SL / max_hold + per-year + walk-forward 4-chunk.
Banding vs 5m pullback (RECENT WR59/EV+0.023). 1m = TF lebih kecil, trend-EMA disesuaikan."""
import scalping_v1 as S
import numpy as np, pandas as pd

df=S.load('1m')
print(f"1m: {len(df)} bar, {df.dt.min()} -> {df.dt.max()}, BTC ${df.close.min():.0f}-${df.close.max():.0f}")
print(f"TP fixed ${S.TP_USD:.0f}, fee {S.FEE*100:.2f}%  (avg $200 = {200/df.close.mean()*100:.2f}%)\n")

def wf(df,t,k=4):
    n=len(df); out=[]
    for j in range(k):
        lo,hi=int(n*j/k),int(n*(j+1)/k); tt=t[(t.xb>=lo)&(t.xb<hi)]
        if len(tt): out.append((len(tt),round((tt.net>0).mean()*100,1),round(tt.net.mean()*100,3)))
        else: out.append((0,0,0))
    return out

print("=== PULLBACK 1m: sweep EMA-trend (RSI35/65, SL$250, hold120, cd5) ===")
for el in [200,400,800]:
    t=S.backtest(df,signal="pullback",sl_usd=250,cooldown=5,max_hold=120,ema_len=el,os_lvl=35,ob_lvl=65)
    S.report(df,t,f"EMA{el}")

print("\n=== best EMA: sweep SL (TP$200, hold120) ===")
BEST_EMA=400
for sl in [150,200,250,300]:
    t=S.backtest(df,signal="pullback",sl_usd=sl,cooldown=5,max_hold=120,ema_len=BEST_EMA,os_lvl=35,ob_lvl=65)
    S.report(df,t,f"SL${sl}")

print("\n=== sweep max_hold (SL$250) ===")
for mh in [30,60,120,240]:
    t=S.backtest(df,signal="pullback",sl_usd=250,cooldown=5,max_hold=mh,ema_len=BEST_EMA,os_lvl=35,ob_lvl=65)
    S.report(df,t,f"hold{mh}")

print("\n=== RSI level (SL$250, hold120) ===")
for os_,ob_ in [(30,70),(35,65),(40,60),(25,75)]:
    t=S.backtest(df,signal="pullback",sl_usd=250,cooldown=5,max_hold=120,ema_len=BEST_EMA,os_lvl=os_,ob_lvl=ob_)
    S.report(df,t,f"RSI{os_}/{ob_}")

print("\n=== WALK-FORWARD 4-chunk (best guess: EMA400 SL250 hold120 RSI35/65) ===")
t=S.backtest(df,signal="pullback",sl_usd=250,cooldown=5,max_hold=120,ema_len=BEST_EMA,os_lvl=35,ob_lvl=65)
for i,(nn,wr,ev) in enumerate(wf(df,t)):
    print(f"  chunk{i+1}: n{nn} WR{wr}% EV{ev:+.3f}%")
r=S.report(df,t,"FULL")
