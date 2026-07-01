#!/usr/bin/env python3
"""ara_grid.py — fokus thread MOMENTUM-CONTINUATION (ride saham hot) + exit asimetris.
Momentum = WR rendah tapi winner besar -> kunci = potong rugi cepat, biar winner lari (trail)."""
import os,glob,heapq,itertools
import numpy as np, pandas as pd
import ara

D=os.path.join(os.path.dirname(os.path.abspath(__file__)),"data_lowcap")
data={}
for f in glob.glob(os.path.join(D,"*.JK.csv")):
    sym=os.path.basename(f)[:-4]
    try:
        d=pd.read_csv(f,parse_dates=['dt'])
        if len(d)>=300: data[sym]=d
    except Exception: pass
print(f"universe {len(data)} saham low-cap\n")

# precompute features sekali per saham
FEA={sym:ara.features(df) for sym,df in data.items()}

def pooled(setup_fn, cf):
    rows=[]
    for sym,df in data.items():
        mask=setup_fn(FEA[sym])
        t,_=ara.backtest_setup(df,mask,cf)
        if len(t):
            dts=df['dt'].to_numpy()
            for _,r in t.iterrows(): rows.append((dts[int(r['eb'])],dts[int(r['xb'])],float(r['net'])))
    if not rows: return None
    T=pd.DataFrame(rows,columns=['ed','xd','net']); x=T['net'].to_numpy()
    gp=x[x>0].sum();gl=-x[x<0].sum()
    # portfolio K=6
    Ts=T.sort_values('ed');cash=1.0;inv=0.0;op=[];curve=[]
    for _,r in Ts.iterrows():
        ed=r['ed']
        while op and op[0][0]<=ed: xd,a,pn=heapq.heappop(op);cash+=a*(1+pn);inv-=a;curve.append((xd,cash+inv))
        if len(op)>=6 or cash<=1e-9: continue
        tot=cash+inv;a=min(tot/6,cash);cash-=a;inv+=a;heapq.heappush(op,(r['xd'],a,r['net']))
    while op: xd,a,pn=heapq.heappop(op);cash+=a*(1+pn);inv-=a;curve.append((xd,cash+inv))
    eq=cash+inv;cur=pd.DataFrame(curve,columns=['dt','eq']).sort_values('dt')
    pk=np.maximum.accumulate(cur['eq'].to_numpy());dd=((pk-cur['eq'].to_numpy())/pk).max()*100
    return dict(n=len(x),wr=round((x>0).mean()*100,1),mean=round(x.mean()*100,3),
                pf=round(gp/gl,2) if gl>0 else 99.9,cagr=round((eq**(1/6.4)-1)*100,1),dd=round(dd,1),
                tot=round(x.sum()*100,0))

# saringan momentum-continuation: prior_ara>=pa, breakout opsional, filter likuiditas + tier harga
def make_setup(pa, need_bo, vmin, price_lo, price_hi):
    def fn(F):
        m=(F['prior_ara']>=pa)&(F['volval']>=vmin)&(F['c']>=price_lo)&(F['c']<=price_hi)
        if need_bo: m=m&F['breakout']
        return m
    return fn

print("=== ENTRY x EXIT grid (momentum-continuation) ===")
print(f"{'pa':>2} {'bo':>2} {'vmin':>5} {'tp':>3} {'sl':>3} {'mh':>2} {'gb':>3} | {'n':>4} {'WR%':>5} {'mean%':>6} {'PF':>5} {'CAGR':>6} {'DD':>5}")
best=[]
for pa,need_bo in [(2,True),(2,False),(3,True),(1,True)]:
  for vmin in [1e9,3e9]:
    setup=make_setup(pa,need_bo,vmin,50,5000)
    for tp,sl,mh,gb in itertools.product([20,30,0],[5,7],[3,5,8],[4,6]):
        cf=dict(tp=tp,sl=sl,max_hold=mh,trail_giveback=gb,trail_act=6,use_trail=True,slip=0.005)
        r=pooled(setup,cf)
        if r and r['n']>=60:
            best.append((pa,need_bo,vmin,tp,sl,mh,gb,r))
best.sort(key=lambda z:-z[7]['mean'])
for pa,bo,vmin,tp,sl,mh,gb,r in best[:15]:
    print(f"{pa:>2} {str(bo)[0]:>2} {vmin:>5.0e} {tp:>3} {sl:>3} {mh:>2} {gb:>3} | {r['n']:>4} {r['wr']:>5} {r['mean']:>+6.2f} {r['pf']:>5} {r['cagr']:>6} {r['dd']:>5}")
print(f"\n{len(best)} config n>=60. Top by expectancy di atas.")
