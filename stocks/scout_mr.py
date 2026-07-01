#!/usr/bin/env python3
"""scout_mr.py — sweep IN-SAMPLE param mean-reversion (mr_rsi) utk cari region profitabel
& ukur headroom (dgn vs tanpa fee). BUKAN validasi final (itu nanti: OOS/holdout/perturb)."""
import os,glob,time,itertools
import numpy as np, pandas as pd
import seng

HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(HERE,"data")
data={}
for f in glob.glob(os.path.join(DATA,"*.JK.csv")):
    sym=os.path.basename(f)[:-4]
    try:
        d=pd.read_csv(f,parse_dates=['dt'])
        if len(d)>=300: data[sym]=d
    except Exception: pass
print(f"universe: {len(data)} saham\n")

def expectancy(data, cf):
    nets=[]
    for df in data.values():
        _,t=seng.run(df,cf)
        if len(t): nets.append(t['net'].to_numpy())
    if not nets: return None
    x=np.concatenate(nets); n=len(x)
    if n<120: return None
    wr=(x>0).mean()*100; mean=x.mean()*100
    gp=x[x>0].sum(); gl=-x[x<0].sum(); pf=gp/gl if gl>0 else np.inf
    tot=x.sum()*100   # additive PnL (% poin, robust)
    return dict(n=n,wr=wr,mean=mean,pf=pf,tot=tot)

# grid mr_rsi
grid=dict(
    rsi_len=[2,3,4],
    rsi_buy=[5,10,15,20,25],
    sma_exit=[3,5],
    rsi_exit=[55,65,75],
    tp=[0.0,5.0,10.0],
    sl=[0.0,10.0],
)
keys=list(grid); combos=list(itertools.product(*[grid[k] for k in keys]))
print(f"grid mr_rsi: {len(combos)} kombinasi x {len(data)} saham ...")
t0=time.time(); rows=[]
for vals in combos:
    cf=dict(zip(keys,vals)); cf['mode']='mr_rsi'; cf['sma_trend']=200
    r=expectancy(data,cf)
    if r and r['wr']>=58 and r['n']>=150:
        rows.append((cf,r))
print(f"selesai {time.time()-t0:.0f}s, {len(rows)} config lolos WR>=58 & n>=150\n")

rows.sort(key=lambda x:-x[1]['mean'])      # ranking by expectancy (net fee)
print("=== TOP 12 by expectancy (NET fee IDX) ===")
print(f"{'rsi_len':>7} {'buy':>4} {'smaEx':>5} {'rsiEx':>5} {'tp':>4} {'sl':>4} | {'n':>5} {'WR%':>5} {'mean%':>7} {'PF':>5} {'totPnL%':>8}")
for cf,r in rows[:12]:
    print(f"{cf['rsi_len']:>7} {cf['rsi_buy']:>4} {cf['sma_exit']:>5} {cf['rsi_exit']:>5} {cf['tp']:>4.0f} {cf['sl']:>4.0f} | "
          f"{r['n']:>5} {r['wr']:>5.1f} {r['mean']:>7.3f} {r['pf']:>5.2f} {r['tot']:>8.0f}")

# headroom: top config TANPA fee
if rows:
    best=rows[0][0]; nofee=dict(best); nofee['fee_buy']=0; nofee['fee_sell']=0
    rn=expectancy(data,nofee)
    print(f"\nHEADROOM (config terbaik TANPA fee): WR={rn['wr']:.1f}% mean={rn['mean']:.3f}% PF={rn['pf']:.2f} totPnL={rn['tot']:.0f}")
    print(f"  -> drag fee per trade ~{rows[0][1]['mean']-rn['mean']:.3f}%  (gap yg harus ditutup edge)")
