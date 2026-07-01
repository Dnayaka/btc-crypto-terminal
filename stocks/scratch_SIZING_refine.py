import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import pf
import numpy as np

data = pf.load_data()
cf = dict(pf.CAND)
T = pf.all_trades(data, cf)

# Fine leverage sweep across all K to find true max CAGR under DD caps.
Ks=[3,4,5,6,8]
levs=[round(x,2) for x in np.arange(1.0,3.01,0.1)]
rows=[]
for K in Ks:
    for L in levs:
        p=pf.portfolio(T,K=K,lev=L)
        rows.append((K,L,p['cagr'],p['dd']))

def best_under(cap):
    cand=[r for r in rows if r[3]<=cap]
    return max(cand,key=lambda r:r[2]) if cand else None

for cap in [25.0,20.0,15.0,12.0]:
    b=best_under(cap)
    if b: print(f"DD<={cap:>5}: BEST K={b[0]} lev={b[1]}  CAGR={b[2]:.2f}%  DD={b[3]:.1f}%")

# efficiency ratio leaderboard (CAGR/DD) at the constraint-binding points per K
print("\n=== per-K: max CAGR hitting DD~25 and DD~15 ===")
for K in Ks:
    sub=[r for r in rows if r[0]==K]
    b25=max([r for r in sub if r[3]<=25.0],key=lambda r:r[2],default=None)
    b15=max([r for r in sub if r[3]<=15.0],key=lambda r:r[2],default=None)
    s25=f"lev{b25[1]} CAGR{b25[2]:.1f}/DD{b25[3]:.1f}" if b25 else "n/a"
    s15=f"lev{b15[1]} CAGR{b15[2]:.1f}/DD{b15[3]:.1f}" if b15 else "n/a"
    print(f"K={K}:  @DD25 {s25:>28}   @DD15 {s15:>28}")
