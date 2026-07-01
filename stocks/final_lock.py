#!/usr/bin/env python3
"""final_lock.py — ukur FORMULA GABUNGAN (deploy universe+gate likuiditas + entry SMA50-rising
+union RSI2) secara utuh di universe penuh, lalu validasi final + frontier risiko + regime opsional.
Sintesis dari workflow idx-mr-pushlimit (5/6 lensa lolos audit)."""
import os,json,itertools
import numpy as np, pandas as pd
import pf, seng

data=pf.load_data(); print(f"universe: {len(data)} saham\n")

BASE   = dict(pf.CAND)   # mr_rsi rsi4<15 sma_exit5 tp10 sl20 maxhold10 sma_trend200 min_close50
# FINAL = BASE + deploy(gate likuiditas) + entry(union RSI2 + filter SMA50-naik)
FINAL  = dict(BASE); FINAL.update(rsi_buy=19.0, rsi2_or=5.0, req_sma50_rising=True, sma50_rise_win=5,
                                  min_volval=1e10)

def show(tag, cf, K=5, lev=1.0):
    r=pf.evaluate(cf, K=K, lev=lev)
    f=r['full']; h=r['holdout']; p=r['portfolio']
    print(f"{tag}")
    print(f"  full   : WR {f['wr']}%  mean {f['mean']:+}%  PF {f['pf']}  n {f['n']}")
    print(f"  holdout: WR {h['wr']}%  mean {h['mean']:+}%  PF {h['pf']}  n {h['n']}")
    print(f"  port K={K} lev={lev}: CAGR {p['cagr']}%  DD {p['dd']}%  x{p['final']}  (taken {p['taken']} skip {p['skip']})")
    print(f"  per_year_min {r['per_year_min']:+}%  perturb {r['perturb']}  saham_profit {r['n_sym_profit']}")
    return r

print("="*70); print("BASELINE (CAND) di universe penuh:"); print("="*70)
rb=show("baseline", BASE)
print("\n"+"="*70); print("FINAL (deploy+entry) di universe penuh:"); print("="*70)
rf=show("FINAL", FINAL)

print("\n== PER-TAHUN (FINAL) ==")
for y,m in rf['per_year'].items(): print(f"  {y}: {m:+.3f}%/trade")

print("\n== KONSENTRASI (FINAL) ==")
T=pf.all_trades(data,FINAL)
per=T.groupby('sym')['net'].sum().sort_values(ascending=False)
prof=(per>0).sum()
print(f"  {prof}/{len(per)} saham profit ({prof/len(per)*100:.0f}%) · top3 {list(per.head(3).index)} = {per.head(3).sum()/per.sum()*100:.0f}% PnL")
# drop top-3 -> masih positif?
keep=set(per.index)-set(per.head(3).index)
Tk=T[T['sym'].isin(keep)]; pk=pf.portfolio(Tk,K=5)
print(f"  tanpa top-3: CAGR {pk['cagr']}% (harus tetap positif = edge broad)")

print("\n== FRONTIER RISIKO (FINAL: K-slot x leverage) -> pilih sesuai selera ==")
print(f"  {'':6}" + "".join(f"lev{l:<6}" for l in [1.0,1.5,2.0]))
for K in [3,4,5,6,8]:
    row=f"  K={K:<3} "
    for lev in [1.0,1.5,2.0]:
        p=pf.evaluate(FINAL,K=K,lev=lev)['portfolio']
        row+=f"{p['cagr']:>4.0f}%/DD{p['dd']:<3.0f}"
    print(row)

print("\n== +REGIME IHSG opsional (cuma entry saat IHSG>SMA100) ==")
idx=pf.index_df()
if idx is not None:
    c=idx['close'].to_numpy(); s100=seng.sma(c,100); idx=idx.assign(reg=c>s100)
    regmap=dict(zip(idx['dt'].to_numpy(), idx['reg'].to_numpy()))
    Tr=T.copy(); Tr['reg']=Tr['ed'].map(lambda d: regmap.get(d, True))
    Ton=Tr[Tr['reg']]
    pon=pf.portfolio(Ton,K=5); son=pf.stats(Ton)
    pyr={int(y):round(g['net'].mean()*100,3) for y,g in Ton.groupby(pd.to_datetime(Ton['xd']).dt.year)}
    print(f"  FINAL+regime: WR {son['wr']}% mean {son['mean']:+}% n {son['n']} | CAGR {pon['cagr']}% DD {pon['dd']}% | pmin {min(pyr.values()):+}%")
    print(f"    per-year: {pyr}")

# simpan formula final
out=dict(name="IDX Mean-Reversion v1 (dip-in-uptrend)", universe_size=len(data),
         config=FINAL, baseline_cagr=rb['portfolio']['cagr'], final_cagr=rf['portfolio']['cagr'],
         full=rf['full'], holdout=rf['holdout'], per_year=rf['per_year'], perturb=rf['perturb'])
json.dump(out, open(os.path.join(os.path.dirname(__file__),"formula.json"),"w"), indent=1, default=str)
print("\n-> formula.json disimpan.")
