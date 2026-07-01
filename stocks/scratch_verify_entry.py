#!/usr/bin/env python3
"""INDEPENDENT adversarial verification of lens-ENTRY candidate.

Candidate (from approach description):
  Entry = dip oversold (RSI4<19 OR RSI2<5) GATED by trend-quality filter
          'SMA50 rising' (SMA50 > SMA50[5 days ago]), on top of base mr_rsi
          regime (close>SMA200) + liquidity (min_close>=50). Base RSI gate disabled.
  Claim: WR 66.4%, holdout_mean 0.903, CAGR 13.47% (K=5,lev=1), DD 7.5%,
         perturb 1, per_year_min 0.39.

I re-derive the entry mask MYSELF (not importing their build_mask_filt) using only
seng's rsi/sma primitives (those ARE the strategy definitions). I test on the FROZEN
48-sym snapshot (apples-to-apples with claim) AND the CURRENT 76-sym universe (OOU).
"""
import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import os, glob, json
import numpy as np, pandas as pd
import pf, seng

SNAP = "/tmp/claude-1000/-home-dnayaka/38e6bacd-d0e9-4982-be14-2d9c4c3936b3/scratchpad/snap"

def load_dir(d, min_bars=300):
    out={}
    for f in glob.glob(os.path.join(d,"*.JK.csv")):
        sym=os.path.basename(f)[:-4]
        try:
            x=pd.read_csv(f,parse_dates=['dt'])
            if len(x)>=min_bars: out[sym]=x
        except Exception: pass
    return out

snap = load_dir(SNAP)
cur  = load_dir(pf.DATA)
print(f"frozen snapshot syms={len(snap)}  current universe syms={len(cur)}")

# ---- INDEPENDENT entry mask: (RSI4<rthr OR RSI2<deep) AND SMA50 rising over rise days ----
def entry_mask(df, rlen=4, rthr=19, deep_len=2, deep_thr=5, rise_L=50, rise_k=5):
    c = df['close'].to_numpy(float)
    R_shallow = seng.rsi(c, rlen)
    R_deep    = seng.rsi(c, deep_len)
    oversold  = (R_shallow < rthr) | (R_deep < deep_thr)
    s50 = seng.sma(c, rise_L)
    s50_prev = np.roll(s50, rise_k)
    rising = s50 > s50_prev          # NaN compares False -> safe at warmup
    return oversold & rising

def run_trades(data, mp):
    """Apply mask as extra_long on base mr_rsi cf with base RSI gate disabled."""
    cf = dict(pf.CAND); cf['rsi_buy'] = 100.0
    if 'sma_exit' in mp: cf['sma_exit'] = mp['sma_exit']
    rows=[]
    for sym,df in data.items():
        m = entry_mask(df, rlen=mp.get('rlen',4), rthr=mp.get('rthr',19),
                       deep_len=mp.get('deep_len',2), deep_thr=mp.get('deep_thr',5),
                       rise_L=mp.get('rise_L',50), rise_k=mp.get('rise_k',5))
        c2 = dict(cf); c2['extra_long'] = m
        try: _,t = seng.run(df,c2)
        except Exception: continue
        if not len(t): continue
        dts = df['dt'].to_numpy()
        for _,r in t.iterrows():
            rows.append((dts[int(r['eb'])],dts[int(r['xb'])],float(r['net']),sym))
    return pd.DataFrame(rows,columns=['ed','xd','net','sym'])

def report(data, mp, tag, K=5, lev=1.0):
    T = run_trades(data, mp)
    full = pf.stats(T)
    hold = pf.stats(T[T['xd']>=np.datetime64('2024-01-01')])
    py = pf.per_year(T); pmin = min(py.values()) if py else 0.0
    port = pf.portfolio(T,K=K,lev=lev)
    nsym = int((T.groupby('sym')['net'].sum()>0).sum()) if len(T) else 0
    # concentration: share of total POSITIVE-sum pnl from top-3 symbols
    conc = None; topshare=None
    if len(T):
        bysym = T.groupby('sym')['net'].sum().sort_values(ascending=False)
        tot = T['net'].sum()
        top3 = bysym.head(3).sum()
        topshare = round(top3/tot,2) if tot!=0 else None
        conc = list(bysym.head(5).round(3).items())
    print(f"\n[{tag}]")
    print(f"  full : n={full['n']} WR={full['wr']} mean={full['mean']} pf={full['pf']} tot={full['tot']}")
    print(f"  hold : n={hold['n']} WR={hold['wr']} mean={hold['mean']} pf={hold['pf']}")
    print(f"  port : CAGR={port['cagr']} DD={port['dd']} final={port['final']} taken={port['taken']} skip={port['skip']}")
    print(f"  per_year={ {k:round(v,3) for k,v in py.items()} }  pmin={pmin}")
    print(f"  nsym_profit={nsym}  top3_pnl_share={topshare}  top5_bysym={conc}")
    return dict(full=full,hold=hold,port=port,py=py,pmin=pmin,nsym=nsym,T=T,topshare=topshare)

WIN = dict(rlen=4, rthr=19, deep_len=2, deep_thr=5, rise_L=50, rise_k=5)

print("\n========== REPRODUCE CLAIM (frozen 48-sym snapshot, K=5 lev=1) ==========")
r_snap = report(snap, WIN, "WINNER @ frozen snapshot")

print("\n========== INDEPENDENT (current 76-sym universe) ==========")
r_cur = report(cur, WIN, "WINNER @ current universe")

# sanity: baseline mr_rsi CAND (no custom mask) for context
print("\n========== context: baseline mr_rsi CAND ==========")
for nm,dd in [("snap",snap),("cur",cur)]:
    Tb = pf.all_trades(dd, dict(pf.CAND))
    fb = pf.stats(Tb); pb = pf.portfolio(Tb,K=5,lev=1.0)
    print(f"  baseline@{nm}: n={fb['n']} WR={fb['wr']} mean={fb['mean']} CAGR={pb['cagr']} DD={pb['dd']}")

# ---------- PERTURBATION (custom): vary mask params + exit; plateau = frac pass ----------
print("\n========== PERTURBATION (mean>0 & WR>=60 = pass) ==========")
def perturb(data):
    npass60=npass65=ntot=0; cagrs=[]; worst=None
    for rthr in [18,19,20]:
        for dr in [4,5,6]:
            for k in [3,5,8]:
                for L in [40,50,60]:
                    for se in [4,5,6]:
                        mp=dict(rlen=4,rthr=rthr,deep_len=2,deep_thr=dr,rise_L=L,rise_k=k,sma_exit=se)
                        T=run_trades(data,mp); f=pf.stats(T); p=pf.portfolio(T,K=5,lev=1.0)
                        ntot+=1
                        npass60+=(f['mean']>0 and f['wr']>=60)
                        npass65+=(f['mean']>0 and f['wr']>=65)
                        cagrs.append(p['cagr'])
                        if worst is None or p['cagr']<worst[1]: worst=(mp,p['cagr'],f['wr'])
    return npass60/ntot, npass65/ntot, cagrs, worst
for nm,dd in [("snap",snap),("cur",cur)]:
    p60,p65,cg,worst=perturb(dd)
    print(f"  {nm}: neighbors=81 pass(WR>=60)={p60:.2f} pass(WR>=65)={p65:.2f} "
          f"CAGR[min={min(cg):.2f} med={np.median(cg):.2f} max={max(cg):.2f}]")

# ---------- concentration stress: drop top-N pnl symbols, recheck ----------
print("\n========== CONCENTRATION STRESS (drop top symbols) ==========")
def drop_top(r, data, mp, nmax=3):
    T=r['T'].copy()
    bysym=T.groupby('sym')['net'].sum().sort_values(ascending=False)
    for ndrop in [1,2,3]:
        drop=set(bysym.head(ndrop).index)
        T2=T[~T['sym'].isin(drop)]
        f=pf.stats(T2); p=pf.portfolio(T2,K=5,lev=1.0)
        print(f"  drop top{ndrop} {sorted(drop)}: n={f['n']} WR={f['wr']} mean={f['mean']} CAGR={p['cagr']} DD={p['dd']}")
drop_top(r_cur, cur, WIN)

print("\n========== DONE ==========")
