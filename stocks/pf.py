#!/usr/bin/env python3
"""pf.py — tool EVAL BERSAMA (dipakai semua skrip riset/agent biar hasil komparabel & anti-look-ahead).
load_data() -> {sym:df} · all_trades(data,cf,lo,hi) · stats(T) · portfolio(T,K) · evaluate(cf).

Objektif riset = MAKSIMALKAN holdout-mean & portfolio-CAGR, syarat WR>=65, per-year-min sehat,
perturbasi plateau. JANGAN optimasi di full-sample saja (itu jebakan overfit)."""
import os,glob,heapq,itertools
import numpy as np, pandas as pd
import seng

HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(HERE,"data")

# kandidat dasar mean-reversion tervalidasi (plateau-robust). Override via cf.
CAND=dict(mode='mr_rsi', rsi_len=4, rsi_buy=15.0, sma_exit=5, rsi_exit=65.0,
          sma_trend=200, tp=10.0, sl=20.0, max_hold=10, min_close=50.0)

_CACHE=None
def load_data(min_bars=300):
    global _CACHE
    if _CACHE is not None: return _CACHE
    d={}
    for f in glob.glob(os.path.join(DATA,"*.JK.csv")):
        sym=os.path.basename(f)[:-4]
        try:
            x=pd.read_csv(f,parse_dates=['dt'])
            if len(x)>=min_bars: d[sym]=x
        except Exception: pass
    _CACHE=d; return d

def index_df():
    p=os.path.join(DATA,"_JKSE.csv")
    return pd.read_csv(p,parse_dates=['dt']) if os.path.exists(p) else None

def all_trades(data, cf, lo=None, hi=None):
    rows=[]
    for sym,df in data.items():
        try: _,t=seng.run(df,cf)
        except Exception: continue
        if not len(t): continue
        dts=df['dt'].to_numpy()
        for _,r in t.iterrows():
            rows.append((dts[int(r['eb'])],dts[int(r['xb'])],float(r['net']),sym))
    T=pd.DataFrame(rows,columns=['ed','xd','net','sym'])
    if lo is not None: T=T[T['xd']>=np.datetime64(lo)]
    if hi is not None: T=T[T['xd']<np.datetime64(hi)]
    return T.reset_index(drop=True)

def stats(T):
    if len(T)==0: return dict(n=0,wr=0.0,mean=0.0,pf=0.0,tot=0.0)
    x=T['net'].to_numpy(); gp=x[x>0].sum(); gl=-x[x<0].sum()
    return dict(n=int(len(x)),wr=round((x>0).mean()*100,1),mean=round(x.mean()*100,3),
                pf=round(gp/gl,2) if gl>0 else 99.9,tot=round(x.sum()*100,1))

def portfolio(T, K=5, lev=1.0, start='2020-01-01', end='2026-06-30'):
    if len(T)==0: return dict(final=1.0,ret=0.0,cagr=0.0,dd=0.0,taken=0,skip=0)
    Ts=T.sort_values('ed').reset_index(drop=True)
    cash=1.0; inv=0.0; op=[]; curve=[]; taken=skip=0
    for _,r in Ts.iterrows():
        ed=r['ed']
        while op and op[0][0]<=ed:
            xd,a,pn=heapq.heappop(op); cash+=a*(1+lev*pn); inv-=a; curve.append((xd,cash+inv))
        if len(op)>=K or cash<=1e-9: skip+=1; continue
        tot=cash+inv; a=min(tot/K,cash); cash-=a; inv+=a
        heapq.heappush(op,(r['xd'],a,r['net'])); taken+=1
    while op:
        xd,a,pn=heapq.heappop(op); cash+=a*(1+lev*pn); inv-=a; curve.append((xd,cash+inv))
    eq=cash+inv; cur=pd.DataFrame(curve,columns=['dt','eq']).sort_values('dt')
    pk=np.maximum.accumulate(cur['eq'].to_numpy()); dd=((pk-cur['eq'].to_numpy())/pk).max()*100
    yrs=max((Ts['xd'].max()-Ts['ed'].min()).days/365.25, 0.25)   # C7: span trade NYATA (bukan window tetap 6.5y -> CAGR adil lintas config)
    return dict(final=round(eq,3),ret=round((eq-1)*100,1),cagr=round((eq**(1/yrs)-1)*100,2),
                dd=round(dd,1),taken=taken,skip=skip)

def per_year(T):
    if len(T)==0: return {}
    return {int(y):round(g['net'].mean()*100,3) for y,g in T.groupby(pd.to_datetime(T['xd']).dt.year)}

def perturb(cf, data=None, deltas=None):
    """Fraksi tetangga param yg tetap (mean>0 & WR>=60). >=0.8 = plateau."""
    data=data or load_data()
    base=dict(CAND); base.update(cf); pos=0; tot=0
    rls=[max(2,base['rsi_len']-1),base['rsi_len'],base['rsi_len']+1]
    rbs=[base['rsi_buy']-3,base['rsi_buy'],base['rsi_buy']+3]
    ses=[max(2,base['sma_exit']-1),base['sma_exit'],base['sma_exit']+1]
    for rl,rb,se in itertools.product(rls,rbs,ses):
        c=dict(base); c.update(rsi_len=rl,rsi_buy=float(rb),sma_exit=se); s=stats(all_trades(data,c))
        tot+=1; pos+=(s['mean']>0 and s['wr']>=60)
    return round(pos/tot,2)

def evaluate(cf, data=None, K=5, lev=1.0, do_perturb=True):
    """Ringkasan komparabel: full / holdout(2024-26) / portfolio / per-year-min / perturbasi."""
    data=data or load_data(); base=dict(CAND); base.update(cf)
    T=all_trades(data,base); full=stats(T)
    hold=stats(all_trades(data,base,lo='2024-01-01'))
    py=per_year(T); pmin=min(py.values()) if py else 0.0
    p=portfolio(T,K=K,lev=lev)
    out=dict(config=base, full=full, holdout=hold, portfolio=p,
             per_year=py, per_year_min=pmin,
             n_sym_profit=int((T.groupby('sym')['net'].sum()>0).sum()) if len(T) else 0)
    if do_perturb: out['perturb']=perturb(cf,data)
    return out

if __name__=='__main__':
    import json
    r=evaluate(CAND)
    print(json.dumps({k:v for k,v in r.items() if k!='config'},default=str,indent=1))
