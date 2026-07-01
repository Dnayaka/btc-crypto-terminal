import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
"""LENS REGIME — index (IHSG/^JKSE) regime entry filter for the MR strategy.

WINNER: keep an MR trade only if, on the day BEFORE entry (no look-ahead), the index is
either in a healthy uptrend (SMA100 slope rising) OR deeply oversold (>15% off its
trailing-252d peak = capitulation). Skips the dangerous middle: index rolling over but
not yet washed out (early-decline knife-catching, e.g. Jan-Feb 2026 ATH -> -10%).

Decompose proved both legs matter: SMA100-slope leg cuts the 2021-2023 grind drawdown and
fixes 2023; the dd<-15 'capitulation escape' adds back the high-WR (74%) bounce trades the
pure-trend gate would discard -> keeps/raises CAGR and lifts 2026.

Needs custom code (per-date index regime + post-filter on all_trades); NOT a cf override.
Filter is applied preserving all_trades' canonical (symbol-grouped) order so portfolio()
numbers match pf.evaluate exactly (greedy K-slot fill is tie-order sensitive)."""
import numpy as np, pandas as pd
import pf

def build_regime(idx):
    def sma(x,n): return pd.Series(x).rolling(n).mean().to_numpy()
    ix=idx.copy().sort_values('dt').reset_index(drop=True)
    c=ix['close'].to_numpy(float)
    ix['sma100']=sma(c,100)
    ix['peak252']=pd.Series(c).rolling(252,min_periods=20).max().to_numpy()
    ix['ddfrom']=(c/ix['peak252']-1.0)*100
    s=ix['sma100'].to_numpy(); ix['sl100']=s>np.roll(s,5)
    reg=ix[['dt','sl100','ddfrom']].copy()
    reg['sl100']=reg['sl100'].shift(1); reg['ddfrom']=reg['ddfrom'].shift(1)  # prior-day -> no look-ahead
    reg['idt']=reg['dt']
    return reg.sort_values('idt').reset_index(drop=True)

def regime_filter(T0, reg, ddth=-15.0):
    """Boolean keep-mask aligned to T0's ORIGINAL (canonical) row order."""
    tmp=T0.reset_index().rename(columns={'index':'oid'}).sort_values('ed')
    mm=pd.merge_asof(tmp, reg, left_on='ed', right_on='idt', direction='backward')
    mm['keep']=((mm['sl100']==True)|(mm['ddfrom']<ddth)).fillna(True)
    return mm.set_index('oid')['keep'].reindex(range(len(T0))).to_numpy()

if __name__=='__main__':
    pf._CACHE=None
    data=pf.load_data(); reg=build_regime(pf.index_df())
    T0=pf.all_trades(data, pf.CAND)
    W=T0[regime_filter(T0,reg,-15.0)].reset_index(drop=True)
    for nm,T in [('BASELINE',T0),('WINNER sl100|dd<-15',W)]:
        f=pf.stats(T); h=pf.stats(T[T['xd']>=np.datetime64('2024-01-01')])
        py=pf.per_year(T); p=pf.portfolio(T,K=5,lev=1.0)
        print(f"{nm}: n={f['n']} WR={f['wr']} mean={f['mean']} hold={h['mean']} "
              f"CAGR={p['cagr']} DD={p['dd']} pmin={round(min(py.values()),3)}")
        print("   per_year:",{k:round(float(v),3) for k,v in py.items()})
