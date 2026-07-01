#!/usr/bin/env python3
"""Independent adversarial verification of the 'exit' lens candidate.
Candidate config_json: {"sma_exit": 4, "tp": 6, "max_hold": 10}
Claims: WR 65.7%, holdout_mean 0.623, CAGR 9.09% (K=5, lev=1), DD 15.4%,
        perturb 0.96, per_year_min -0.21.
"""
import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import json
import numpy as np, pandas as pd
import pf, seng

CFG = json.loads('{"sma_exit": 4, "tp": 6, "max_hold": 10}')
K, LEV = 5, 1.0   # claim says K=5 lev=1

DATA = pf.load_data()
print(f"[snapshot] {len(DATA)} symbols loaded\n")

# ---- 1) canonical reproduction via pf.evaluate (exact path orchestrator uses) ----
ev = pf.evaluate(CFG, K=K, lev=LEV)
print("=== pf.evaluate(CFG, K=5, lev=1) ===")
print("  full:    ", ev['full'])
print("  holdout: ", ev['holdout'])
print("  portfolio:", ev['portfolio'])
print("  per_year:", ev['per_year'])
print("  per_year_min:", ev['per_year_min'])
print("  perturb:", ev['perturb'])
print("  n_sym_profit:", ev['n_sym_profit'])

CLAIM = dict(wr=65.7, hmean=0.623, cagr=9.09, dd=15.4, perturb=0.96, pmin=-0.21)
print("\n=== CLAIM vs REPRODUCED ===")
print(f"  WR:      claim {CLAIM['wr']:>7} | repro {ev['full']['wr']:>7}")
print(f"  hmean:   claim {CLAIM['hmean']:>7} | repro {ev['holdout']['mean']:>7}")
print(f"  CAGR:    claim {CLAIM['cagr']:>7} | repro {ev['portfolio']['cagr']:>7}")
print(f"  DD:      claim {CLAIM['dd']:>7} | repro {ev['portfolio']['dd']:>7}")
print(f"  perturb: claim {CLAIM['perturb']:>7} | repro {ev['perturb']:>7}")
print(f"  pmin:    claim {CLAIM['pmin']:>7} | repro {ev['per_year_min']:>7}")

# ---- 2) build full trade table for deeper tests ----
base = dict(pf.CAND); base.update(CFG)
T = pf.all_trades(DATA, base)
print(f"\n[trades] total rows={len(T)}")

# ---- 3) holdout 2024-2026: mean must be > 0 ----
Th = T[T['xd'] >= np.datetime64('2024-01-01')]
hstat = pf.stats(Th)
print(f"\n=== HOLDOUT 2024-2026 ===  n={hstat['n']} wr={hstat['wr']} mean={hstat['mean']} tot={hstat['tot']}")
print("  holdout mean>0:", hstat['mean'] > 0)

# ---- 4) perturbation plateau ----
print(f"\n=== PERTURB === {ev['perturb']}  (>=0.8 plateau)")

# ---- 5) per-year ----
print(f"\n=== PER-YEAR === min={ev['per_year_min']}")
for y, v in sorted(ev['per_year'].items()):
    print(f"   {y}: {v}")

# ---- 6) CONCENTRATION: is PnL driven by <=3 symbols? ----
print("\n=== CONCENTRATION (per-symbol total net) ===")
g = T.groupby('sym')['net'].agg(['sum', 'count']).sort_values('sum', ascending=False)
total = g['sum'].sum()
print(f"  total summed net (all syms) = {total*100:.1f}%  across {len(g)} symbols")
top = g.head(5)
print("  TOP 5 contributors:")
for sym, row in top.iterrows():
    print(f"     {sym}: net={row['sum']*100:+7.1f}%  n={int(row['count'])}  share={row['sum']/total*100:5.1f}%")
top3_share = g['sum'].head(3).sum() / total * 100
print(f"  TOP-3 share of total net = {top3_share:.1f}%")
# also: how many symbols positive vs negative
npos = (g['sum'] > 0).sum(); nneg = (g['sum'] < 0).sum()
print(f"  symbols positive={npos} negative={nneg}")
# robustness: recompute portfolio CAGR after dropping top-3 symbols
drop3 = set(g['sum'].head(3).index)
T_no3 = T[~T['sym'].isin(drop3)]
p_no3 = pf.portfolio(T_no3, K=K, lev=LEV)
print(f"  CAGR after dropping top-3 syms = {p_no3['cagr']} (DD {p_no3['dd']}, n={len(T_no3)})")

# ---- 7) leverage honesty: portfolio at K=5 lev=1 DD; and what happens scaling lev ----
print("\n=== LEVERAGE / DD honesty ===")
for lv in (1.0, 1.5, 2.0):
    p = pf.portfolio(T, K=K, lev=lv)
    print(f"   lev={lv}: CAGR {p['cagr']} DD {p['dd']} taken={p['taken']} skip={p['skip']}")

# ---- 8) sanity: compare to BASELINE (CAND, no exit retune) ----
Tb = pf.all_trades(DATA, dict(pf.CAND))
pb = pf.portfolio(Tb, K=K, lev=LEV)
sb = pf.stats(Tb)
print(f"\n=== BASELINE CAND === wr={sb['wr']} mean={sb['mean']} CAGR={pb['cagr']} DD={pb['dd']} n={sb['n']}")
print(f"=== CANDIDATE     === wr={ev['full']['wr']} mean={ev['full']['mean']} CAGR={ev['portfolio']['cagr']} DD={ev['portfolio']['dd']} n={ev['full']['n']}")
