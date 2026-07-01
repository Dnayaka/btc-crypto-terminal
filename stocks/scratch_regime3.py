import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import numpy as np, pandas as pd
import pf, seng

data = pf.load_data()
idx = pf.index_df()
ix = idx.copy().sort_values('dt').reset_index(drop=True)
c = ix['close'].to_numpy(float)
def sma(x,n):
    s=pd.Series(x); return s.rolling(n).mean().to_numpy()
ix['sma20']=sma(c,20); ix['sma50']=sma(c,50); ix['sma100']=sma(c,100); ix['sma200']=sma(c,200)
ix['peak252']=pd.Series(c).rolling(252,min_periods=20).max().to_numpy()
ix['ddfrom']=(c/ix['peak252']-1.0)*100
ix['ret20']=(c/np.roll(c,20)-1.0)*100
ix['ret10']=(c/np.roll(c,10)-1.0)*100
ix['gt100']=c>ix['sma100'].to_numpy()
ix['gt200']=c>ix['sma200'].to_numpy()
s100=ix['sma100'].to_numpy(); ix['sma100_up']=s100>np.roll(s100,5)

regcols=['gt100','gt200','sma100_up','ddfrom','ret20','ret10']
reg=ix[['dt']+regcols].copy()
for col in regcols: reg[col]=reg[col].shift(1)
reg['idt']=reg['dt']

T0 = pf.all_trades(data, pf.CAND).sort_values('ed').reset_index(drop=True)
M=pd.merge_asof(T0, reg.sort_values('idt'), left_on='ed', right_on='idt', direction='backward')

# --- find when portfolio DD happens (baseline) ---
def portfolio_curve(T, K=5, lev=1.0):
    import heapq
    Ts=T.sort_values('ed').reset_index(drop=True)
    cash=1.0; inv=0.0; op=[]; curve=[]
    for _,r in Ts.iterrows():
        ed=r['ed']
        while op and op[0][0]<=ed:
            xd,a,pn=heapq.heappop(op); cash+=a*(1+lev*pn); inv-=a; curve.append((xd,cash+inv))
        if len(op)>=K or cash<=1e-9: continue
        tot=cash+inv; a=min(tot/K,cash); cash-=a; inv+=a
        heapq.heappush(op,(r['xd'],a,r['net']))
    while op:
        xd,a,pn=heapq.heappop(op); cash+=a*(1+lev*pn); inv-=a; curve.append((xd,cash+inv))
    cur=pd.DataFrame(curve,columns=['dt','eq']).sort_values('dt').reset_index(drop=True)
    pk=np.maximum.accumulate(cur['eq'].to_numpy()); dd=(pk-cur['eq'].to_numpy())/pk*100
    cur['dd']=dd
    return cur

cur=portfolio_curve(T0)
imax=cur['dd'].idxmax()
print("=== BASELINE portfolio max DD location ===")
print("max DD %:", round(cur['dd'].max(),2), " at", cur.loc[imax,'dt'])
# show DD>5 windows
hi=cur[cur['dd']>4]
print("periods with DD>4%:")
print(hi.groupby(pd.to_datetime(hi['dt']).dt.to_period('M')).agg(maxdd=('dd','max')).to_string())

def ev(mask,label,K=5):
    Tf=M[mask.fillna(False).to_numpy() if hasattr(mask,'fillna') else mask].reset_index(drop=True)
    full=pf.stats(Tf); hold=pf.stats(Tf[Tf['xd']>=np.datetime64('2024-01-01')])
    py=pf.per_year(Tf); pmin=min(py.values()) if py else 0.0
    p=pf.portfolio(Tf,K=K)
    print(f"{label:30s} keep={len(Tf):3d} WR={full['wr']:.1f} hold={hold['mean']:+.3f} "
          f"CAGR={p['cagr']:.2f} DD={p['dd']:.1f} pmin={pmin:+.2f} y26={py.get(2026,0):+.2f} y23={py.get(2023,0):+.2f}")
    return p,full,py

print("\n=== contrarian / combined index filters ===")
ev(np.ones(len(M),bool),"baseline")
# block index froth (overbought run-up)
for th in [8,10,12,15]:
    ev(M['ret20']<th, f"ret20<{th} (block froth)")
# block deep crash entries
for th in [-20,-25,-30]:
    ev(M['ddfrom']>th, f"ddfrom>{th} (block deep crash)")
# combined: not froth AND not deep crash
ev((M['ret20']<12)&(M['ddfrom']>-25), "ret20<12 & dd>-25")
ev((M['ret20']<10)&(M['ddfrom']>-22), "ret20<10 & dd>-22")
# regime ON but allow deep-oversold MR (gt100 OR deeply oversold)
ev((M['gt100']==True)|(M['ddfrom']<-18), "gt100 OR dd<-18")
ev((M['gt200']==True)|(M['ddfrom']<-15), "gt200 OR dd<-15")
ev((M['sma100_up']==True)|(M['ddfrom']<-18), "sma100_up OR dd<-18")
