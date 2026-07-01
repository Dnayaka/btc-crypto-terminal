import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import pf
import numpy as np

# Baseline candidate config (mean-reversion). Sizing lens: WR/holdout/perturb/per_year_min
# are INVARIANT to K & lev (they are per-trade or trade-level stats). Only portfolio
# CAGR & DD change. So compute trades once, then sweep portfolio(T,K,lev).

data = pf.load_data()
cf = dict(pf.CAND)

# trade-level invariants
T = pf.all_trades(data, cf)
full = pf.stats(T)
hold = pf.stats(pf.all_trades(data, cf, lo='2024-01-01'))
py = pf.per_year(T)
pmin = min(py.values()) if py else 0.0
pert = pf.perturb(cf, data)

print("=== INVARIANTS (unchanged by sizing) ===")
print(f"full WR={full['wr']}  mean={full['mean']}  pf={full['pf']}  n={full['n']}")
print(f"holdout WR={hold['wr']}  mean={hold['mean']}  n={hold['n']}")
print(f"per_year={py}")
print(f"per_year_min={pmin}  perturb={pert}")
print()

Ks = [3,4,5,6,8]
levs = [1.0,1.5,2.0,2.5,3.0]

# Build frontier
grid = {}
print("=== FRONTIER: CAGR (DD) per (K,lev) ===")
hdr = "K\\lev " + "  ".join(f"{L:>14}" for L in levs)
print(hdr)
for K in Ks:
    cells = []
    for L in levs:
        p = pf.portfolio(T, K=K, lev=L)
        grid[(K,L)] = p
        cells.append(f"{p['cagr']:>6.2f}/{p['dd']:>5.1f}dd")
    print(f"K={K:>2}  " + "  ".join(f"{c:>14}" for c in cells))
print()
print("(cell = CAGR% / DD%)")
print()

# Candidates satisfying constraints. WR>=65, holdout mean>0, perturb>=0.8,
# per_year_min>=-1.5 all invariant & passing. Binding constraint = DD.
inv_ok = (full['wr']>=65 and hold['mean']>0 and pert>=0.8 and pmin>=-1.5)
print(f"invariant constraints pass: {inv_ok}  (WR={full['wr']} holdmean={hold['mean']} perturb={pert} pymin={pmin})")
print()

def best_under(maxdd):
    best=None
    for (K,L),p in grid.items():
        if p['dd']<=maxdd:
            if best is None or p['cagr']>grid[best]['cagr']:
                best=(K,L)
    return best

agg = best_under(25.0)
con = best_under(15.0)
print("=== RECOMMENDATIONS ===")
for label,key,cap in [("AGGRESSIVE (DD<=25)",agg,25),("CONSERVATIVE (DD<=15)",con,15)]:
    if key is None:
        print(f"{label}: none under DD<={cap}")
        continue
    K,L=key; p=grid[key]
    print(f"{label}: K={K} lev={L}  CAGR={p['cagr']}%  DD={p['dd']}%  final={p['final']}  taken={p['taken']} skip={p['skip']}")

# also report baseline K=5 lev=1
b=grid[(5,1.0)]
print()
print(f"baseline K=5 lev=1.0: CAGR={b['cagr']}% DD={b['dd']}%")
