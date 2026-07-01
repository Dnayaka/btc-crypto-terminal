#!/usr/bin/env python3
import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import numpy as np, pandas as pd, json, itertools, heapq
import pf, seng

CLAIM = dict(wr=65.8, holdout_mean=0.726, cagr=8.1, dd=15.7, perturb=0.96, per_year_min=-0.337)
CFG_JSON = "{}"   # winning idea = momentum allocation 0 -> MR-only baseline (pf.CAND)

data = pf.load_data()
print(f"universe: {len(data)} symbols loaded")

# ---------------------------------------------------------------
# 1) Independent reproduction of the candidate headline via pf.evaluate
# ---------------------------------------------------------------
cf = json.loads(CFG_JSON)
K, lev = 5, 1.0   # claim states K=5, lev=1
ev = pf.evaluate(cf, K=K, lev=lev)
full = ev['full']; hold = ev['holdout']; port = ev['portfolio']
print("\n=== pf.evaluate(cf={}) reproduction (cf empty -> CAND MR baseline) ===")
print("full     :", full)
print("holdout  :", hold)
print("portfolio:", port)
print("per_year :", ev['per_year'])
print("per_year_min:", ev['per_year_min'])
print("perturb  :", ev['perturb'])
print("n_sym_profit:", ev['n_sym_profit'])

print("\n--- compare vs CLAIM ---")
def cmp(name, got, claim, tol):
    ok = abs(got-claim) <= tol
    print(f"  {name:14s} got={got:8.3f}  claim={claim:8.3f}  tol={tol}  {'OK' if ok else 'MISMATCH'}")
    return ok
r = {}
r['wr']   = cmp('WR',          full['wr'],         CLAIM['wr'],          0.5)
r['hm']   = cmp('holdout_mean',hold['mean'],       CLAIM['holdout_mean'],0.05)
r['cagr'] = cmp('CAGR',        port['cagr'],       CLAIM['cagr'],        0.3)
r['dd']   = cmp('DD',          port['dd'],         CLAIM['dd'],          0.5)
r['pmin'] = cmp('per_year_min',ev['per_year_min'], CLAIM['per_year_min'],0.05)
r['ptb']  = cmp('perturb',     ev['perturb'],      CLAIM['perturb'],     0.05)

# ---------------------------------------------------------------
# 2) Holdout 2024-2026 mean must be > 0
# ---------------------------------------------------------------
T_full = pf.all_trades(data, pf.CAND)
T_hold = pf.all_trades(data, pf.CAND, lo='2024-01-01')
print(f"\n=== holdout 2024-2026 ===  n={len(T_hold)} mean={hold['mean']}  wr={hold['wr']}  >0? {hold['mean']>0}")
ph = pf.portfolio(T_hold, K=5, lev=1.0, start='2024-01-01', end='2026-06-30')
print("holdout portfolio:", ph)

# ---------------------------------------------------------------
# 3) Concentration: is PnL driven by <=3 symbols?
# ---------------------------------------------------------------
print("\n=== CONCENTRATION (trade-level net sum per symbol) ===")
g = T_full.groupby('sym')['net'].agg(['sum','count']).sort_values('sum', ascending=False)
tot = g['sum'].sum()
print(f"total summed net (pp): {tot:.4f}  across {len(g)} symbols")
top = g.head(8).copy(); top['pct_of_total'] = top['sum']/tot*100
print(top)
top3_share = g['sum'].head(3).sum()/tot*100
top1_share = g['sum'].head(1).sum()/tot*100
print(f"top-1 share of total net: {top1_share:.1f}%   top-3 share: {top3_share:.1f}%")
n_pos = (g['sum']>0).sum(); n_neg=(g['sum']<0).sum()
print(f"symbols net-positive: {n_pos} / {len(g)}   net-negative: {n_neg}")

# Drop top-3 contributors and re-evaluate portfolio robustness
top3_syms = list(g.head(3).index)
T_drop = T_full[~T_full['sym'].isin(top3_syms)].reset_index(drop=True)
p_drop = pf.portfolio(T_drop, K=5, lev=1.0)
print(f"portfolio WITHOUT top-3 symbols {top3_syms}: cagr={p_drop['cagr']} dd={p_drop['dd']}  (vs base cagr {port['cagr']})")

# ---------------------------------------------------------------
# 4) Verify the CORE THESIS: momentum allocation = 0 (no portfolio edge)
#    Reproduce two-sleeve blend independently.
# ---------------------------------------------------------------
print("\n=== THESIS CHECK: does ANY momentum sleeve lift the MR-only portfolio? ===")
idx = pf.index_df()
ix = idx.copy(); ic = ix['close'].to_numpy(float)
ix['regime'] = ic > seng.sma(ic,200)
reg = ix.set_index('dt')['regime']
def gate_by_index(T):
    if len(T)==0: return T
    ed = pd.to_datetime(T['ed']); rr = reg.reindex(ed, method='ffill').to_numpy()
    return T[rr==True].reset_index(drop=True)

base_cagr = port['cagr']
print(f"MR-only baseline portfolio CAGR = {base_cagr}")

# two-sleeve weighted daily equity blend (independent pools)
def daily_curve(T, K=5, lev=1.0, start='2020-01-01', end='2026-06-30'):
    # simulate pf.portfolio but return daily equity series
    if len(T)==0: return None
    Ts=T.sort_values('ed').reset_index(drop=True)
    cash=1.0; inv=0.0; op=[]; pts=[]
    for _,row in Ts.iterrows():
        ed=row['ed']
        while op and op[0][0]<=ed:
            xd,a,pn=heapq.heappop(op); cash+=a*(1+lev*pn); inv-=a; pts.append((xd,cash+inv))
        if len(op)>=K or cash<=1e-9: continue
        totv=cash+inv; a=min(totv/K,cash); cash-=a; inv+=a
        heapq.heappush(op,(row['xd'],a,row['net']))
    while op:
        xd,a,pn=heapq.heappop(op); cash+=a*(1+lev*pn); inv-=a; pts.append((xd,cash+inv))
    s=pd.DataFrame(pts,columns=['dt','eq']).sort_values('dt')
    s=s.groupby('dt')['eq'].last()
    full_idx=pd.date_range(start,end,freq='D')
    return s.reindex(full_idx, method='ffill').fillna(1.0)

mr_curve = daily_curve(T_full)
# build a few momentum sleeves (best-effort from approach description)
mom_cfgs = {
 'bo50_breakout': dict(mode='momentum',bo_len=50,sma_fast=50,sma_trend=200,tp=0.0,sl=15.0,max_hold=40,min_close=50.0),
 'bo20_tight'   : dict(mode='momentum',bo_len=20,sma_fast=50,sma_trend=200,tp=10.0,sl=12.0,max_hold=20,min_close=50.0),
 'gated_bo55'   : dict(mode='momentum',bo_len=55,sma_fast=50,sma_trend=150,tp=20.0,sl=12.0,max_hold=40,min_close=50.0),
 'sma_pull'     : dict(mode='sma_pull',sma_fast=50,sma_trend=200,tp=0.0,sl=12.0,max_hold=20,min_close=50.0),
}
def cagr_of(curve):
    yrs=(pd.Timestamp('2026-06-30')-pd.Timestamp('2020-01-01')).days/365.25
    return (curve.iloc[-1]**(1/yrs)-1)*100
def dd_of(curve):
    pk=np.maximum.accumulate(curve.to_numpy()); return ((pk-curve.to_numpy())/pk).max()*100

print(f"{'sleeve':16s}{'stand_cagr':>11}{'best_blend_cagr':>16}{'best_w':>8}{'lift?':>7}")
any_lift=False
for name,mc in mom_cfgs.items():
    Tm = pf.all_trades(data, mc)
    if name=='gated_bo55': Tm = gate_by_index(Tm)
    if len(Tm)<20:
        print(f"{name:16s}{'n<20':>11}"); continue
    pm = pf.portfolio(Tm, K=5, lev=1.0)
    mom_curve = daily_curve(Tm)
    best=(-99,0)
    for w in [0.0,0.05,0.1,0.15,0.2,0.3,0.4]:
        blend = (1-w)*mr_curve + w*mom_curve
        cg = cagr_of(blend)
        if cg>best[0]: best=(cg,w)
    lift = best[0] > base_cagr + 0.05
    any_lift = any_lift or lift
    print(f"{name:16s}{pm['cagr']:>11.2f}{best[0]:>16.2f}{best[1]:>8.2f}{str(lift):>7}")
print(f"ANY momentum sleeve lifts MR-only blend? {any_lift}  (thesis 'alloc=0' holds if False)")

# ---------------------------------------------------------------
# 5) honest DD at lev=1
# ---------------------------------------------------------------
print(f"\n=== DD honesty (lev={lev}) === portfolio DD = {port['dd']}%  (<=25%? {port['dd']<=25})")

print("\nRESULT FLAGS:", json.dumps(dict(
  reproduced=all([r['wr'],r['cagr'],r['dd']]),
  holdout_pos=bool(hold['mean']>0),
  perturb_ok=bool(ev['perturb']>=0.8),
  pmin_ok=bool(ev['per_year_min']>=-1.5),
  concentration_top3_pct=round(float(top3_share),1),
  drop_top3_cagr=p_drop['cagr'],
  thesis_alloc0_holds=not any_lift,
), default=str))
