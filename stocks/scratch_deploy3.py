#!/usr/bin/env python3
"""scratch_deploy3.py — finalisasi: config deploy terbaik {min_volval} di universe 76, K=5.
Cek perturb (plateau), plateau di sekitar min_volval, dan detail penuh. Juga K-lever bonus."""
import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import pf, json

pf._CACHE=None
big=pf.load_data()
print("N=",len(big))

print("\n--- plateau min_volval (perturb penuh), K=5 ---")
for mv in [7e9,1e10,1.3e10,1.5e10]:
    r=pf.evaluate({'min_volval':mv},data=big,K=5,lev=1.0,do_perturb=True)
    p=r['portfolio']; f=r['full']; h=r['holdout']
    print(f"mv={mv:>9.1e} | fullWR {f['wr']:.1f} n={f['n']} | hoMean {h['mean']:+.3f} "
          f"| CAGR {p['cagr']:+.2f} DD {p['dd']:.1f} | pmin {r['per_year_min']:+.2f} | perturb {r['perturb']}")

print("\n--- BEST = min_volval 1e10, detail K=5 ---")
r=pf.evaluate({'min_volval':1e10},data=big,K=5,lev=1.0)
print(json.dumps({k:v for k,v in r.items() if k!='config'}, default=str, indent=1))

print("\n--- K-lever bonus pada min_volval 1e10 (cek DD<=25) ---")
for K in [3,4,5]:
    r=pf.evaluate({'min_volval':1e10},data=big,K=K,lev=1.0,do_perturb=False)
    p=r['portfolio']
    print(f"K={K} | CAGR {p['cagr']:+.2f} DD {p['dd']:.1f} taken {p['taken']} skip {p['skip']}")
