#!/usr/bin/env python3
import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import json, numpy as np
import pf

DATA=pf.load_data(); print(f"[snapshot] {len(DATA)} symbols")
WIN={"sma_exit":4,"tp":6,"max_hold":10}

# canonical evaluate (same as orchestrator would call)
r=pf.evaluate(WIN, K=5, lev=1.0)
b=pf.evaluate({},  K=5, lev=1.0)
def line(tag,e):
    print(f"{tag:14s} full wr={e['full']['wr']} mean={e['full']['mean']} n={e['full']['n']} | "
          f"hold wr={e['holdout']['wr']} mean={e['holdout']['mean']} | "
          f"port cagr={e['portfolio']['cagr']} dd={e['portfolio']['dd']} | "
          f"pmin={e['per_year_min']:+.2f} perturb={e['perturb']}")
line("BASELINE",b); line("WIN(se4tp6)",r)

# leveraged deployment for max CAGR within DD<=25
T=pf.all_trades(DATA,{**pf.CAND,**WIN})
for K,lev in [(5,1.0),(6,2.0),(4,1.25),(8,2.5)]:
    p=pf.portfolio(T,K=K,lev=lev)
    print(f"   deploy K={K} lev={lev}: CAGR {p['cagr']} DD {p['dd']}")
print("config_json =", json.dumps(WIN))
