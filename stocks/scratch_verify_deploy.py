#!/usr/bin/env python3
"""scratch_verify_deploy.py — AUDIT INDEPENDEN kandidat lens 'deploy'.
config_json={"min_volval": 1e10} pada universe 76 saham, K=5, lev=1.
Reproduksi klaim + uji ketahanan: holdout, perturb, per_year, KONSENTRASI, DD."""
import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import json
import numpy as np, pandas as pd
import pf

CF = json.loads('{"min_volval": 10000000000}')
K, LEV = 5, 1.0

# fresh cache (independen)
pf._CACHE = None
data = pf.load_data()
print("N saham termuat:", len(data))

NEW = ['BBTN.JK','BNGA.JK','MEGA.JK','PNBN.JK','BJBR.JK','BJTM.JK','MAPA.JK','ERAA.JK','RALS.JK','LPPF.JK',
       'SCMA.JK','MNCN.JK','TBIG.JK','WTON.JK','PTPP.JK','ADHI.JK','SMRA.JK','SSMS.JK','LSIP.JK','AALI.JK',
       'DSNG.JK','TINS.JK','NCKL.JK','ESSA.JK','PGEO.JK','ELSA.JK','KKGI.JK','HRUM.JK']
present_new = sorted([s for s in NEW if s in data])
print("midcap baru hadir:", len(present_new), "dari", len(NEW))

# ---------- 1. REPRODUKSI KLAIM ----------
print("\n=== 1. REPRODUKSI evaluate(cf, K=5, lev=1) ===")
r = pf.evaluate(CF, data=data, K=K, lev=LEV, do_perturb=True)
full, hold, p = r['full'], r['holdout'], r['portfolio']
print(f" full   : n={full['n']} WR={full['wr']} mean={full['mean']}")
print(f" holdout: n={hold['n']} WR={hold['wr']} mean={hold['mean']}")
print(f" portf  : CAGR={p['cagr']} DD={p['dd']} taken={p['taken']} skip={p['skip']} final={p['final']}")
print(f" per_year={r['per_year']}  per_year_min={r['per_year_min']}")
print(f" perturb={r['perturb']}  n_sym_profit={r['n_sym_profit']}")

claim = dict(WR=66.4, holdout_mean=1.008, CAGR=9.56, DD=14.7, perturb=1.0, pmin=-0.177)
print("\n KLAIM vs REPRO:")
print(f"  WR          klaim {claim['WR']}   repro {full['wr']}")
print(f"  holdout_mean klaim {claim['holdout_mean']} repro {hold['mean']}")
print(f"  CAGR        klaim {claim['CAGR']}  repro {p['cagr']}")
print(f"  DD          klaim {claim['DD']}   repro {p['dd']}")
print(f"  perturb     klaim {claim['perturb']}    repro {r['perturb']}")
print(f"  per_year_min klaim {claim['pmin']} repro {r['per_year_min']}")

# ---------- 2. HOLDOUT 2024-2026 mean>0 ----------
print("\n=== 2. HOLDOUT 2024-2026 ===")
Tho = pf.all_trades(data, dict(pf.CAND, **CF), lo='2024-01-01')
sho = pf.stats(Tho)
print(f" holdout n={sho['n']} WR={sho['wr']} mean={sho['mean']} pf={sho['pf']} tot={sho['tot']}")
print(f" holdout mean>0 ? {sho['mean'] > 0}")

# ---------- 3. KONSENTRASI ----------
print("\n=== 3. KONSENTRASI (apakah PnL didorong <=3 saham?) ===")
T = pf.all_trades(data, dict(pf.CAND, **CF))
bysym = T.groupby('sym')['net'].agg(['sum','count','mean']).sort_values('sum', ascending=False)
tot_net = T['net'].sum()
print(f" total trade={len(T)}  jumlah saham aktif={T['sym'].nunique()}  total sum(net)={tot_net*100:.1f}%")
print(" TOP-8 kontributor (sum net %):")
for s, row in bysym.head(8).iterrows():
    print(f"   {s:9s} sum={row['sum']*100:+7.1f}%  n={int(row['count']):3d}  mean={row['mean']*100:+.3f}%  share={row['sum']/tot_net*100:5.1f}%")
top3 = bysym.head(3)['sum'].sum()
print(f" share top-3 dari total sum(net) = {top3/tot_net*100:.1f}%")

# portfolio TANPA top-3 kontributor (drop dari trade pool)
top3_syms = list(bysym.head(3).index)
Tdrop = T[~T['sym'].isin(top3_syms)].reset_index(drop=True)
p_drop = pf.portfolio(Tdrop, K=K, lev=LEV)
sho_drop = pf.stats(Tdrop[Tdrop['xd'] >= np.datetime64('2024-01-01')])
print(f" drop top-3 {top3_syms}: CAGR {p['cagr']} -> {p_drop['cagr']}  | holdout mean {hold['mean']} -> {sho_drop['mean']}")

# portfolio TANPA top-5
top5_syms = list(bysym.head(5).index)
Tdrop5 = T[~T['sym'].isin(top5_syms)].reset_index(drop=True)
p_drop5 = pf.portfolio(Tdrop5, K=K, lev=LEV)
print(f" drop top-5 {top5_syms}: CAGR {p['cagr']} -> {p_drop5['cagr']}")

# konsentrasi holdout: top-3 di 2024-2026
hbysym = Tho.groupby('sym')['net'].sum().sort_values(ascending=False)
print(f" holdout top-3 saham: {[ (s, round(v*100,1)) for s,v in hbysym.head(3).items() ]}")
print(f" holdout total sum={Tho['net'].sum()*100:+.1f}%  share top-3={hbysym.head(3).sum()/Tho['net'].sum()*100:.1f}%")

# ---------- 4. PERTURB plateau ----------
print("\n=== 4. PERTURB ===")
print(f" perturb(cf) = {r['perturb']}  (>=0.8 plateau)")

# ---------- 5. DD jujur (lev=1) ----------
print("\n=== 5. DD ===")
print(f" DD K=5 lev=1 = {p['dd']}%  (<=25 ? {p['dd'] <= 25})")
for kk in [3,4,5,6]:
    pp = pf.portfolio(T, K=kk, lev=LEV)
    print(f"   K={kk}: CAGR {pp['cagr']} DD {pp['dd']} taken {pp['taken']} skip {pp['skip']}")

# ---------- 6. apakah gate benar memperbaiki? (cf vs no-gate, 76 universe) ----------
print("\n=== 6. EFEK GATE (76 universe, K=5) ===")
r0 = pf.evaluate({}, data=data, K=K, lev=LEV, do_perturb=False)
print(f" tanpa gate: WR {r0['full']['wr']} hoMean {r0['holdout']['mean']} CAGR {r0['portfolio']['cagr']} DD {r0['portfolio']['dd']}")
print(f" dgn  gate : WR {full['wr']} hoMean {hold['mean']} CAGR {p['cagr']} DD {p['dd']}")
