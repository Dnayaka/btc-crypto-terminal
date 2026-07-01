#!/usr/bin/env python3
import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import numpy as np, pandas as pd
import pf, seng

DATA = pf.load_data()
print(f"[snapshot] {len(DATA)} symbols")

def trades(cf_over):
    cf=dict(pf.CAND); cf.update(cf_over); return pf.all_trades(DATA,cf), cf

def base_stats(T):
    full=pf.stats(T); hold=pf.stats(T[T['xd']>=np.datetime64('2024-01-01')])
    py=pf.per_year(T); pmin=min(py.values()) if py else 0.0
    return full,hold,py,pmin

CFG={
 "BASELINE":   {},
 "se4_mh10_tp6": dict(sma_exit=4,max_hold=10,tp=6.0),
 "se5_mh10_tp6": dict(sma_exit=5,max_hold=10,tp=6.0),
 "se5_mh7_tp6":  dict(sma_exit=5,max_hold=7, tp=6.0),
}

for tag,cf in CFG.items():
    T,full_cf=trades(cf)
    full,hold,py,pmin=base_stats(T)
    pert=pf.perturb(cf,DATA)
    print(f"\n=== {tag}  wr={full['wr']} mean={full['mean']} hmean={hold['mean']} pmin={pmin:+.2f} perturb={pert} n={full['n']}")
    print("   per_year:",{k:round(v,2) for k,v in py.items()})
    # K x lev sweep -> maximize CAGR with DD<=24 (margin under 25)
    best=None
    for K in (4,5,6,8):
        row=f"   K={K}: "
        for lev in (1.0,1.25,1.5,1.75,2.0,2.5):
            p=pf.portfolio(T,K=K,lev=lev)
            row+=f"L{lev}->cagr{p['cagr']:.1f}/dd{p['dd']:.0f}  "
            if p['dd']<=24 and (best is None or p['cagr']>best[2]):
                best=(K,lev,p['cagr'],p['dd'])
        print(row)
    if best: print(f"   >> MAX-CAGR @ DD<=24: K={best[0]} lev={best[1]} -> CAGR {best[2]:.2f} DD {best[3]:.1f}")
