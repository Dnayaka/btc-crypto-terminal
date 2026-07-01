#!/usr/bin/env python3
import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import numpy as np, pandas as pd, itertools, json, heapq
import pf, seng

data = pf.load_data()
T_mr = pf.all_trades(data, pf.CAND)
idx = pf.index_df()
START='2020-01-01'; END='2026-06-30'

# index regime: ^JKSE close > its SMA200 (market in uptrend)
ix = idx.copy()
ic = ix['close'].to_numpy(float)
ix['regime'] = ic > seng.sma(ic,200)
reg = ix.set_index('dt')['regime']

def gate_by_index(T):
    """keep only trades whose ENTRY date falls on an index-uptrend day."""
    if len(T)==0: return T
    ed = pd.to_datetime(T['ed'])
    r = reg.reindex(ed, method='ffill').to_numpy()
    return T[r==True].reset_index(drop=True)

def cm(T,K=5,lev=1.0):
    if len(T)==0: return dict(n=0,wr=0,mean=0,cagr=0,dd=0,pmin=0,final=1)
    s=pf.stats(T); p=pf.portfolio(T,K=K,lev=lev)
    py=pf.per_year(T); pmin=min(py.values()) if py else 0
    return dict(n=s['n'],wr=s['wr'],mean=s['mean'],cagr=p['cagr'],dd=p['dd'],pmin=pmin,final=p['final'])

print("=== index-regime-gated momentum standalone (only breakout when ^JKSE>SMA200) ===")
print(f"{'cfg':30s}{'n':>5}{'WR':>6}{'mean':>8}{'cagr':>7}{'dd':>6}{'pmin':>6}")
mom_grid=[]
for bo in [30,40,55,65]:
    for trd in [100,150,200]:
        for tp in [0.0,20.0,30.0]:
            for sl in [12.0,15.0]:
                for mh in [20,40]:
                    cf=dict(mode='momentum',bo_len=bo,sma_fast=50,sma_trend=trd,tp=tp,sl=sl,max_hold=mh,min_close=50.0)
                    T=gate_by_index(pf.all_trades(data,cf))
                    if len(T)<60: continue
                    m=cm(T); mom_grid.append((cf,m))
mom_grid.sort(key=lambda x:-x[1]['cagr'])
for cf,m in mom_grid[:12]:
    tag=f"bo{cf['bo_len']} t{cf['sma_trend']} tp{cf['tp']:.0f} sl{cf['sl']:.0f} mh{cf['max_hold']}"
    print(f"{tag:30s}{m['n']:>5}{m['wr']:>6.1f}{m['mean']:>8.3f}{m['cagr']:>7.2f}{m['dd']:>6.1f}{m['pmin']:>6.2f}")

print(f"\nMR-only baseline: cagr 8.10 dd 15.7 WR 65.8 (target to beat: CAGR>8.1)")

# take best gated momentum, test concat blend + small-weight conclusion
if mom_grid:
    bestcf=mom_grid[0][0]
    Tmom=gate_by_index(pf.all_trades(data,bestcf))
    print(f"\nBest gated momentum standalone CAGR={mom_grid[0][1]['cagr']} (must exceed 8.1 to lift blend)")
    Tall=pd.concat([T_mr,Tmom],ignore_index=True)
    s=pf.stats(Tall); p=pf.portfolio(Tall,K=5); py=pf.per_year(Tall)
    print(f"CONCAT blend: fullWR {s['wr']:.1f} n {s['n']} | cagr {p['cagr']} dd {p['dd']} pmin {min(py.values()):.2f}")
