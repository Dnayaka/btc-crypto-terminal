#!/usr/bin/env python3
"""scratch_deploy2.py — kontrol: apakah CAGR-gain benar dari universe besar (bukan artefak K)?
Bandingkan 48-lama vs 76-besar pada K sama. Plus uji liquidity-gate min_volval (deploy-level)."""
import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import pf

NEW=['BBTN.JK','BNGA.JK','MEGA.JK','PNBN.JK','BJBR.JK','BJTM.JK','MAPA.JK','ERAA.JK','RALS.JK','LPPF.JK',
     'SCMA.JK','MNCN.JK','TBIG.JK','WTON.JK','PTPP.JK','ADHI.JK','SMRA.JK','SSMS.JK','LSIP.JK','AALI.JK',
     'DSNG.JK','TINS.JK','NCKL.JK','ESSA.JK','PGEO.JK','ELSA.JK','KKGI.JK','HRUM.JK']

pf._CACHE=None
big=pf.load_data()
old={s:d for s,d in big.items() if s not in NEW}
print(f"old N={len(old)}  big N={len(big)}")

def line(tag,r,K):
    p=r['portfolio']; f=r['full']; h=r['holdout']
    print(f"{tag:14s} K={K} | fullWR {f['wr']:.1f} n={f['n']} | hoMean {h['mean']:+.3f} "
          f"| CAGR {p['cagr']:+.2f} DD {p['dd']:.1f} | taken {p['taken']} skip {p['skip']} | pmin {r['per_year_min']:+.2f}")

print("\n--- 48-LAMA vs 76-BESAR, K sama (lev=1) ---")
for K in [3,4,5]:
    line("48-lama", pf.evaluate(pf.CAND,data=old,K=K,lev=1.0,do_perturb=False),K)
    line("76-besar",pf.evaluate(pf.CAND,data=big,K=K,lev=1.0,do_perturb=False),K)
    print()

print("--- liquidity-gate min_volval (76-besar, K=5) ---")
for mv in [0, 5e9, 1e10, 2e10, 5e10, 1e11]:
    cf=dict(min_volval=mv)
    r=pf.evaluate(cf,data=big,K=5,lev=1.0,do_perturb=False)
    p=r['portfolio']; f=r['full']; h=r['holdout']
    print(f"min_volval={mv:>10.0e} | fullWR {f['wr']:.1f} n={f['n']} | hoMean {h['mean']:+.3f} "
          f"| CAGR {p['cagr']:+.2f} DD {p['dd']:.1f} | pmin {r['per_year_min']:+.2f}")
