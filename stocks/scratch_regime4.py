import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import numpy as np, pandas as pd, itertools
import pf, seng

pf._CACHE=None
data=pf.load_data(); idx=pf.index_df()
def sma(x,n):
    s=pd.Series(x); return s.rolling(n).mean().to_numpy()
ix=idx.copy().sort_values('dt').reset_index(drop=True)
c=ix['close'].to_numpy(float)
for n in (50,100,200): ix[f'sma{n}']=sma(c,n)
ix['peak252']=pd.Series(c).rolling(252,min_periods=20).max().to_numpy()
ix['ddfrom']=(c/ix['peak252']-1.0)*100
for n in (50,100,200):
    s=ix[f'sma{n}'].to_numpy(); ix[f'sl{n}']=s>np.roll(s,5)  # sma slope up
regcols=['sl50','sl100','sl200','ddfrom']
reg=ix[['dt']+regcols].copy()
for col in regcols: reg[col]=reg[col].shift(1)
reg['idt']=reg['dt']; reg=reg.sort_values('idt').reset_index(drop=True)

def filt(T, slcol, ddth):
    Ts=T.sort_values('ed').reset_index(drop=True)
    m=pd.merge_asof(Ts,reg,left_on='ed',right_on='idt',direction='backward')
    if slcol is None: msk=(m['ddfrom']<ddth)
    elif ddth is None: msk=(m[slcol]==True)
    else: msk=(m[slcol]==True)|(m['ddfrom']<ddth)
    return Ts[msk.fillna(True).to_numpy()].reset_index(drop=True)

def row(label,T,K=5,lev=1.0):
    full=pf.stats(T); hold=pf.stats(T[T['xd']>=np.datetime64('2024-01-01')])
    py=pf.per_year(T); pmin=min(py.values()) if py else 0.0
    p=pf.portfolio(T,K=K,lev=lev)
    print(f"{label:24s} n={len(T):3d} WR={full['wr']:.1f} hold={hold['mean']:+.3f} "
          f"CAGR={p['cagr']:.2f} DD={p['dd']:.1f} pmin={pmin:+.2f} y23={py.get(2023,0):+.2f} y26={py.get(2026,0):+.2f}")
    return p['cagr'],p['dd']

def cperturb(slcol, ddth):
    b=dict(pf.CAND)
    rls=[max(2,b['rsi_len']-1),b['rsi_len'],b['rsi_len']+1]
    rbs=[b['rsi_buy']-3,b['rsi_buy'],b['rsi_buy']+3]
    ses=[max(2,b['sma_exit']-1),b['sma_exit'],b['sma_exit']+1]
    pos=tot=0
    for rl,rb,se in itertools.product(rls,rbs,ses):
        cf=dict(b); cf.update(rsi_len=rl,rsi_buy=float(rb),sma_exit=se)
        Tf=filt(pf.all_trades(data,cf),slcol,ddth)
        s=pf.stats(Tf); tot+=1; pos+=(s['mean']>0 and s['wr']>=60)
    return round(pos/tot,2)

T0=pf.all_trades(data,pf.CAND)
print("=== baseline ===")
row("baseline", T0)
print("\n=== fine dd-threshold scan (sma100_up OR dd<th) ===")
for th in [-11,-12,-13,-14,-15,-16,-17,-18]:
    row(f"sl100 OR dd<{th}", filt(T0,'sl100',th))
print("\n=== SMA-period sensitivity (slope OR dd<-15) ===")
for sc in ['sl50','sl100','sl200']:
    row(f"{sc} OR dd<-15", filt(T0,sc,-15))
print("\n=== decompose ===")
row("sl100 only", filt(T0,'sl100',None))
row("dd<-15 only(no trend)", filt(T0,None,-15))
print("\n=== WINNER perturb + K/lev sensitivity (sl100 OR dd<-15) ===")
W=filt(T0,'sl100',-15)
print("custom perturb:", cperturb('sl100',-15))
for K in [4,5,6,8]:
    row(f"K={K}", W, K=K)
for lev in [1.0,1.5,2.0]:
    row(f"lev={lev}", W, lev=lev)
# holdout-only portfolio (trades entered 2024+)
Wh=W[W['ed']>=np.datetime64('2024-01-01')]
print("\n=== holdout-period only portfolio (ed>=2024) ===")
row("baseline 2024+", T0[T0['ed']>=np.datetime64('2024-01-01')].reset_index(drop=True), )
row("winner 2024+", Wh.reset_index(drop=True))
