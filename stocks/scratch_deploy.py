#!/usr/bin/env python3
"""scratch_deploy.py — DEPLOY lens eval. Universe membesar (48 -> 76 saham).
Bandingkan baseline vs universe-besar pada cf basis (CAND). Sweep K untuk lihat
pemanfaatan slot (modal yg dulu nganggur). JANGAN ubah cf entry/exit (itu lens lain)."""
import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import pf, json

def summ(r):
    return dict(full_wr=float(r['full']['wr']), full_mean=float(r['full']['mean']), full_n=int(r['full']['n']),
                ho_wr=float(r['holdout']['wr']), ho_mean=float(r['holdout']['mean']),
                cagr=float(r['portfolio']['cagr']), dd=float(r['portfolio']['dd']),
                taken=int(r['portfolio']['taken']), skip=int(r['portfolio']['skip']),
                pmin=float(r['per_year_min']), perturb=float(r.get('perturb',0)),
                nsymprofit=int(r['n_sym_profit']))

pf._CACHE=None
data=pf.load_data()
print("N saham termuat:", len(data))
print("simbol baru terdeteksi:", sorted([s for s in data if s in
      ['BBTN.JK','BNGA.JK','MEGA.JK','PNBN.JK','BJBR.JK','BJTM.JK','MAPA.JK','ERAA.JK','RALS.JK','LPPF.JK',
       'SCMA.JK','MNCN.JK','TBIG.JK','WTON.JK','PTPP.JK','ADHI.JK','SMRA.JK','SSMS.JK','LSIP.JK','AALI.JK',
       'DSNG.JK','TINS.JK','NCKL.JK','ESSA.JK','PGEO.JK','ELSA.JK','KKGI.JK','HRUM.JK']]))

print("\n=== cf BASIS (CAND), universe besar, sweep K ===")
for K in [3,4,5,6,8,10]:
    r=pf.evaluate(pf.CAND, data=data, K=K, lev=1.0, do_perturb=(K==5))
    s=summ(r)
    print(f"K={K:2d} | fullWR {s['full_wr']:.1f} mean {s['full_mean']:+.3f} n={s['full_n']} | "
          f"hoWR {s['ho_wr']:.1f} hoMean {s['ho_mean']:+.3f} | CAGR {s['cagr']:+.2f} DD {s['dd']:.1f} "
          f"| taken {s['taken']} skip {s['skip']} | pmin {s['pmin']:+.2f}"
          + (f" perturb {s['perturb']}" if K==5 else ""))

print("\n=== detail K=5 (komparabel baseline) ===")
r=pf.evaluate(pf.CAND, data=data, K=5, lev=1.0)
print(json.dumps({k:v for k,v in r.items() if k!='config'}, default=str, indent=1))
