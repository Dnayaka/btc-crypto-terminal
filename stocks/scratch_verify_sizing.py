import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import json
import numpy as np
import pf

# Candidate from "sizing" lens. config_json = {} -> uses base CAND.
# Claim: WR 66.3%, holdout_mean 0.568, CAGR 18.99% (K=3, lev=1.8),
#        DD 24.1%, perturb 1, per_year_min -0.958.
CFG = json.loads("{}")           # empty -> base CAND
PORT_K = 3
PORT_LEV = 1.8

data = pf.load_data()
print(f"universe size = {len(data)} symbols")

# ---- official evaluate() path (independent reproduction) ----
ev = pf.evaluate(CFG, K=PORT_K, lev=PORT_LEV)
full = ev['full']; hold = ev['holdout']; port = ev['portfolio']
py = ev['per_year']; pmin = ev['per_year_min']; pert = ev['perturb']

print("\n=== REPRODUCTION (pf.evaluate(cf, K=3, lev=1.8)) ===")
print(f"full:    n={full['n']} WR={full['wr']} mean={full['mean']} pf={full['pf']} tot={full['tot']}")
print(f"holdout: n={hold['n']} WR={hold['wr']} mean={hold['mean']}")
print(f"port:    CAGR={port['cagr']} DD={port['dd']} final={port['final']} taken={port['taken']} skip={port['skip']}")
print(f"per_year={py}")
print(f"per_year_min={pmin}  perturb={pert}  n_sym_profit={ev['n_sym_profit']}")

# ---- compare with claims ----
claim = dict(wr=66.3, holdout_mean=0.568, cagr=18.99, dd=24.1, perturb=1.0, pymin=-0.958)
print("\n=== CLAIM vs REPRODUCED ===")
def cmp(name, claimed, got, tol):
    ok = abs(claimed-got) <= tol
    print(f"{name:14s} claim={claimed:>9} got={got:>9}  {'OK' if ok else 'MISMATCH'} (tol {tol})")
    return ok
cmp("WR",          claim['wr'],          full['wr'],  0.5)
cmp("holdout_mean",claim['holdout_mean'],hold['mean'],0.05)
cmp("CAGR",        claim['cagr'],        port['cagr'],0.5)
cmp("DD",          claim['dd'],          port['dd'],  1.0)
cmp("perturb",     claim['perturb'],     pert,        0.05)
cmp("per_year_min",claim['pymin'],       pmin,        0.1)

# ---- leverage / DD honesty: DD at lev=1.0 and across grid ----
T = pf.all_trades(data, dict(pf.CAND))
print("\n=== K x lev frontier (CAGR/DD) — confirm K=3 lev=1.8 sits at DD cap ===")
for K in [3,4,5]:
    cells=[]
    for L in [1.0,1.4,1.8,2.0,2.5]:
        p=pf.portfolio(T,K=K,lev=L)
        cells.append(f"L{L}:{p['cagr']:.1f}/{p['dd']:.1f}")
    print(f"K={K}  " + "   ".join(cells))

p10 = pf.portfolio(T,K=3,lev=1.0)
print(f"\nK=3 lev=1.0 baseline: CAGR={p10['cagr']} DD={p10['dd']}  (lev=1.8 multiplies DD ~1.8x)")

# ---- CONCENTRATION: is PnL driven by <=3 symbols? ----
g = T.groupby('sym')['net'].agg(['sum','count']).sort_values('sum', ascending=False)
total = g['sum'].sum()
top3 = g['sum'].head(3).sum()
top1 = g['sum'].head(1).sum()
print("\n=== CONCENTRATION (per-symbol total net, equal-weight pooled) ===")
print(f"total net (sum of per-trade) = {total:.4f} across {len(g)} symbols")
print(f"top1 share = {top1/total*100:.1f}%   top3 share = {top3/total*100:.1f}%")
print("top 6 contributors:")
for sym,row in g.head(6).iterrows():
    print(f"  {sym:12s} sum={row['sum']:+.4f} ({row['sum']/total*100:+.1f}%)  trades={int(row['count'])}")
print("worst 3:")
for sym,row in g.tail(3).iterrows():
    print(f"  {sym:12s} sum={row['sum']:+.4f} ({row['sum']/total*100:+.1f}%)  trades={int(row['count'])}")

# robustness: drop top-3 symbols, re-run portfolio
drop3 = set(g.head(3).index)
T_drop = T[~T['sym'].isin(drop3)].reset_index(drop=True)
pdrop = pf.portfolio(T_drop, K=3, lev=1.8)
print(f"\nportfolio WITHOUT top-3 symbols: CAGR={pdrop['cagr']} DD={pdrop['dd']} (vs {port['cagr']}/{port['dd']})")

# ---- holdout sign across years ----
print("\n=== holdout 2024-2026 ===")
Th = pf.all_trades(data, dict(pf.CAND), lo='2024-01-01')
print(f"holdout n={len(Th)} stats={pf.stats(Th)}")
print(f"holdout mean>0 ? {pf.stats(Th)['mean']>0}")
