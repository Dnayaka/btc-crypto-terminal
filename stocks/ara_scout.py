#!/usr/bin/env python3
"""ara_scout.py — baseline beberapa 'saringan' pra-ARA di universe low-cap (fill realistis).
Lihat: ada edge net-slippage? berapa entri hilang krn ARA-lock (tak fillable)?"""
import os,glob,heapq
import numpy as np, pandas as pd
import ara

HERE=os.path.dirname(os.path.abspath(__file__)); D=os.path.join(HERE,"data_lowcap")
data={}
for f in glob.glob(os.path.join(D,"*.JK.csv")):
    sym=os.path.basename(f)[:-4]
    try:
        d=pd.read_csv(f,parse_dates=['dt'])
        if len(d)>=300: data[sym]=d
    except Exception: pass
print(f"universe low-cap: {len(data)} saham\n")

def pooled(setup_fn, cf=None, K=6):
    rows=[]; sk=0
    for sym,df in data.items():
        F=ara.features(df); mask=setup_fn(F)
        t,s=ara.backtest_setup(df,mask,cf); sk+=s
        if len(t):
            dts=df['dt'].to_numpy()
            for _,r in t.iterrows(): rows.append((dts[int(r['eb'])],dts[int(r['xb'])],float(r['net']),sym))
    T=pd.DataFrame(rows,columns=['ed','xd','net','sym'])
    st=ara.stats(T.rename(columns={}).assign())  if False else None
    # stats manual
    if len(T)==0: return dict(n=0),0,T
    x=T['net'].to_numpy();gp=x[x>0].sum();gl=-x[x<0].sum()
    s=dict(n=len(x),wr=round((x>0).mean()*100,1),mean=round(x.mean()*100,3),
           pf=round(gp/gl,2) if gl>0 else 99.9,tot=round(x.sum()*100,0),med=round(np.median(x)*100,2),
           nsym=T['sym'].nunique())
    return s,sk,T

def port(T,K=6):
    if len(T)==0: return dict(cagr=0,dd=0,final=1)
    Ts=T.sort_values('ed'); cash=1.0;inv=0.0;op=[];curve=[]
    for _,r in Ts.iterrows():
        ed=r['ed']
        while op and op[0][0]<=ed:
            xd,a,pn=heapq.heappop(op);cash+=a*(1+pn);inv-=a;curve.append((xd,cash+inv))
        if len(op)>=K or cash<=1e-9: continue
        tot=cash+inv;a=min(tot/K,cash);cash-=a;inv+=a;heapq.heappush(op,(r['xd'],a,r['net']))
    while op: xd,a,pn=heapq.heappop(op);cash+=a*(1+pn);inv-=a;curve.append((xd,cash+inv))
    eq=cash+inv;cur=pd.DataFrame(curve,columns=['dt','eq']).sort_values('dt')
    pk=np.maximum.accumulate(cur['eq'].to_numpy());dd=((pk-cur['eq'].to_numpy())/pk).max()*100
    yrs=6.4;return dict(cagr=round((eq**(1/yrs)-1)*100,1),dd=round(dd,1),final=round(eq,2))

SETUPS={
 'vol_breakout (vsurge3 & breakout)' : lambda F:(F['vsurge']>=3)&F['breakout']&(~F['is_ara'])&(F['volval']>1e9),
 'vol_surge4 (vsurge4 & >sma20)'     : lambda F:(F['vsurge']>=4)&F['above']&(~F['is_ara'])&(F['volval']>1e9),
 'ara_continuation (is_ara today)'   : lambda F: F['is_ara']&(F['volval']>1e9),
 'consol_breakout (tight & breakout)': lambda F:(F['rng20']<0.30)&F['breakout']&(F['vsurge']>=2)&(F['volval']>1e9),
 'prior_ara_momo (>=2 ARA/10d & bo)' : lambda F:(F['prior_ara']>=2)&F['breakout']&(F['volval']>1e9),
}
print(f"{'setup':40s} {'n':>4} {'WR%':>5} {'mean%':>6} {'med%':>6} {'PF':>5} {'totPnL':>7} {'CAGR':>5} {'DD':>4} {'skipLock':>8}")
for name,fn in SETUPS.items():
    s,sk,T=pooled(fn)
    if s['n']==0: print(f"{name:40s} (no trade)"); continue
    p=port(T)
    print(f"{name:40s} {s['n']:>4} {s['wr']:>5} {s['mean']:>+6.2f} {s['med']:>+6.2f} {s['pf']:>5} {s['tot']:>7.0f} {p['cagr']:>5} {p['dd']:>4} {sk:>8}")
