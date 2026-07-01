#!/usr/bin/env python3
"""validate_mr.py — validasi anti-overfit kandidat mean-reversion + PnL portfolio realistis.
Lapisan: (1) per-tahun & sub-period, (2) TRUE-HOLDOUT (train 2020-23 -> test 2024-26),
(3) perturbasi tetangga param (plateau vs knife-edge), (4) konsentrasi per-saham,
(5) risiko EKOR (worst trades + efek catastrophe-stop), (6) simulasi PORTFOLIO (CAGR/DD)."""
import os,glob,itertools,heapq
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

CAND=dict(mode='mr_rsi', rsi_len=4, rsi_buy=15.0, sma_exit=5, rsi_exit=65.0,
          sma_trend=200, tp=10.0, sl=0.0, max_hold=10, min_close=50.0)

def all_trades(data, cf, dt_lo=None, dt_hi=None):
    rows=[]
    for sym,df in data.items():
        _,t=seng.run(df,cf)
        if not len(t): continue
        dts=df['dt'].to_numpy()
        for _,r in t.iterrows():
            ed=dts[int(r['eb'])]; xd=dts[int(r['xb'])]
            rows.append((ed,xd,float(r['net']),sym))
    T=pd.DataFrame(rows,columns=['ed','xd','net','sym'])
    if dt_lo is not None: T=T[T['xd']>=np.datetime64(dt_lo)]
    if dt_hi is not None: T=T[T['xd']<np.datetime64(dt_hi)]
    return T.reset_index(drop=True)

def stats(T):
    if len(T)==0: return dict(n=0,wr=0,mean=0,pf=0,tot=0)
    x=T['net'].to_numpy(); gp=x[x>0].sum(); gl=-x[x<0].sum()
    return dict(n=len(x),wr=round((x>0).mean()*100,1),mean=round(x.mean()*100,3),
                pf=round(gp/gl,2) if gl>0 else 99.9, tot=round(x.sum()*100,0))

def portfolio(T, K=6, start='2020-01-01', end='2026-06-30'):
    """Equal-weight K-slot, compounding, fee sudah di net. CAGR & maxDD realized."""
    Ts=T.sort_values('ed').reset_index(drop=True)
    cash=1.0; invested=0.0; openpos=[]; curve=[]; taken=skip=0
    for _,r in Ts.iterrows():
        ed=r['ed']
        while openpos and openpos[0][0]<=ed:
            xd,alloc,pnet=heapq.heappop(openpos); cash+=alloc*(1+pnet); invested-=alloc
            curve.append((xd,cash+invested))
        if len(openpos)>=K or cash<=1e-9: skip+=1; continue
        total=cash+invested; alloc=min(total/K,cash); cash-=alloc; invested+=alloc
        heapq.heappush(openpos,(r['xd'],alloc,r['net'])); taken+=1
    while openpos:
        xd,alloc,pnet=heapq.heappop(openpos); cash+=alloc*(1+pnet); invested-=alloc
        curve.append((xd,cash+invested))
    eq=cash+invested
    cur=pd.DataFrame(curve,columns=['dt','eq']).sort_values('dt')
    peak=np.maximum.accumulate(cur['eq'].to_numpy()); dd=((peak-cur['eq'].to_numpy())/peak).max()*100
    yrs=(pd.Timestamp(end)-pd.Timestamp(start)).days/365.25
    cagr=(eq**(1/yrs)-1)*100
    return dict(final=round(eq,2),ret=round((eq-1)*100,0),cagr=round(cagr,1),dd=round(dd,1),taken=taken,skip=skip)

print(f"universe {len(data)} saham · kandidat: RSI{CAND['rsi_len']}<{CAND['rsi_buy']:.0f}, exit close>SMA{CAND['sma_exit']}, NO-stop, uptrend>SMA{CAND['sma_trend']}\n")
T=all_trades(data,CAND)
print("== FULL SAMPLE ==", stats(T))

print("\n== (1) PER-TAHUN (exit year) ==")
for y,g in T.groupby(pd.to_datetime(T['xd']).dt.year):
    s=stats(g); print(f"  {y}: n={s['n']:4d} WR={s['wr']:5.1f}% mean={s['mean']:+.3f}% PF={s['pf']:.2f}")

print("\n== (2) TRUE-HOLDOUT: grid train 2020-2023 -> test 2024-2026 ==")
train=lambda cf: stats(all_trades(data,cf,dt_hi='2024-01-01'))
test =lambda cf: stats(all_trades(data,cf,dt_lo='2024-01-01'))
grid=[]
for rl,rb,se in itertools.product([3,4,5],[10,15,20],[3,5,8]):
    cf=dict(CAND); cf.update(rsi_len=rl,rsi_buy=float(rb),sma_exit=se)
    tr=train(cf)
    if tr['n']>=100: grid.append((cf,tr))
grid.sort(key=lambda x:-x[1]['mean'])
best_tr=grid[0][0]; print(f"  train-best param: RSI{best_tr['rsi_len']}<{best_tr['rsi_buy']:.0f} SMA{best_tr['sma_exit']}  train={grid[0][1]}")
print(f"  -> HOLDOUT 2024-26 utk param itu : {test(best_tr)}")
print(f"  -> HOLDOUT 2024-26 utk kandidat  : {test(CAND)}")

print("\n== (3) PERTURBASI tetangga (plateau?) ==")
nP=0; pos=0
for rl,rb,se in itertools.product([3,4,5],[12,15,18],[4,5,6]):
    cf=dict(CAND); cf.update(rsi_len=rl,rsi_buy=float(rb),sma_exit=se); s=stats(all_trades(data,cf))
    nP+=1; pos+= (s['mean']>0 and s['wr']>=60)
print(f"  {pos}/{nP} tetangga tetap (mean>0 & WR>=60)  -> {'PLATEAU (robust)' if pos>=nP*0.8 else 'knife-edge (waspada)'}")

print("\n== (4) KONSENTRASI per-saham ==")
per=T.groupby('sym')['net'].agg(['count','mean','sum'])
prof=(per['sum']>0).sum()
print(f"  {prof}/{len(per)} saham profitable ({prof/len(per)*100:.0f}%)")
top=per.sort_values('sum',ascending=False)
print("  top3:", [f"{i}+{r['sum']*100:.0f}" for i,r in top.head(3).iterrows()])
print("  bot3:", [f"{i}{r['sum']*100:.0f}" for i,r in top.tail(3).iterrows()])
print(f"  kontribusi top-3 saham: {top.head(3)['sum'].sum()/per['sum'].sum()*100:.0f}% dari total PnL")

print("\n== (5) RISIKO EKOR (NO-stop) ==")
worst=np.sort(T['net'].to_numpy())[:5]*100
print(f"  5 trade terburuk: {[round(w,1) for w in worst]}%")
for cs in [0,15,20,30]:
    cf=dict(CAND); cf['sl']=float(cs); s=stats(all_trades(data,cf))
    tag='(no-stop)' if cs==0 else f'(catastrophe-stop {cs}%)'
    print(f"  sl={cs:>2}% {tag:22s}: WR={s['wr']:.1f}% mean={s['mean']:+.3f}% PF={s['pf']:.2f} n={s['n']}")

print("\n== (6) PORTFOLIO SIM (equal-weight, fee-net) — PnL REALISTIS ==")
for K in [4,6,8,10]:
    p=portfolio(T,K=K); print(f"  K={K:2d} slot: equity x{p['final']} (CAGR {p['cagr']}%/th, maxDD {p['dd']}%) · taken {p['taken']} skip {p['skip']}")
