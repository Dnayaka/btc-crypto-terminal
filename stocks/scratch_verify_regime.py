import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
"""INDEPENDENT adversarial verification of the 'regime' lens candidate.

Claim: filter MR baseline trades, keep trade iff (on prior-day index state)
  index SMA100-slope rising  OR  index >15% off trailing-252d peak.
Claimed: WR 67.2%, holdout_mean 0.775, CAGR 8.62% (K=5,lev=1), DD 14.3%,
         perturb 1, per_year_min -0.337.

I reimplement the regime build from the DESCRIPTION (not their code) and stress-test.
"""
import numpy as np, pandas as pd, itertools, heapq
import pf, seng

pf._CACHE = None
data = pf.load_data()
idx = pf.index_df()

# ---- independent regime construction ----
def build_reg(idx, slope_lb=5):
    ix = idx.copy().sort_values('dt').reset_index(drop=True)
    c = ix['close'].to_numpy(float)
    sma100 = pd.Series(c).rolling(100).mean().to_numpy()
    peak252 = pd.Series(c).rolling(252, min_periods=20).max().to_numpy()
    ddfrom = (c / peak252 - 1.0) * 100.0
    sl100 = sma100 > np.roll(sma100, slope_lb)      # SMA100 higher than slope_lb days ago
    reg = pd.DataFrame({'dt': ix['dt'], 'sl100': sl100, 'ddfrom': ddfrom})
    # prior-day state -> no look-ahead
    reg['sl100'] = reg['sl100'].shift(1)
    reg['ddfrom'] = reg['ddfrom'].shift(1)
    reg['idt'] = reg['dt']
    return reg.sort_values('idt').reset_index(drop=True)

def apply_filter(T0, reg, ddth=-15.0, use_slope=True, use_dd=True):
    """Return filtered T preserving T0 canonical order (so portfolio greedy matches)."""
    tmp = T0.reset_index().rename(columns={'index': 'oid'}).sort_values('ed')
    mm = pd.merge_asof(tmp, reg, left_on='ed', right_on='idt', direction='backward')
    if use_slope and use_dd:
        keep = (mm['sl100'] == True) | (mm['ddfrom'] < ddth)
    elif use_slope:
        keep = (mm['sl100'] == True)
    else:
        keep = (mm['ddfrom'] < ddth)
    keep = keep.fillna(True)               # missing regime (warmup) -> keep, matches their NaN->True
    mm = mm.assign(keep=keep.values)
    out = mm[mm['keep']].sort_values('oid')
    return out[['ed', 'xd', 'net', 'sym']].reset_index(drop=True)

def summary(label, T, K=5, lev=1.0):
    full = pf.stats(T)
    hold = pf.stats(T[T['xd'] >= np.datetime64('2024-01-01')])
    py = pf.per_year(T)
    pmin = min(py.values()) if py else 0.0
    p = pf.portfolio(T, K=K, lev=lev)
    nsym_prof = int((T.groupby('sym')['net'].sum() > 0).sum()) if len(T) else 0
    print(f"{label:30s} n={full['n']:3d} WR={full['wr']:.1f} mean={full['mean']:+.3f} "
          f"hold={hold['mean']:+.3f}(n{hold['n']}) CAGR={p['cagr']:.2f} DD={p['dd']:.1f} "
          f"pmin={pmin:+.3f} nsymprof={nsym_prof}")
    return dict(full=full, hold=hold, py=py, pmin=pmin, p=p, nsym=nsym_prof)

reg = build_reg(idx)
T0 = pf.all_trades(data, pf.CAND)
W = apply_filter(T0, reg, -15.0, True, True)

print("=" * 100)
print("REPRODUCTION")
print("=" * 100)
b = summary("BASELINE (no filter)", T0)
r = summary("WINNER sl100|dd<-15", W)

print("\nClaim: WR 67.2  hold 0.775  CAGR 8.62  DD 14.3  perturb 1  pmin -0.337")
print(f"Repro: WR {r['full']['wr']}  hold {r['hold']['mean']}  CAGR {r['p']['cagr']}  "
      f"DD {r['p']['dd']}  pmin {r['pmin']}")

# ---- perturb (custom: re-run filter for each neighbor) ----
def cperturb(ddth=-15.0):
    base = dict(pf.CAND)
    rls = [max(2, base['rsi_len'] - 1), base['rsi_len'], base['rsi_len'] + 1]
    rbs = [base['rsi_buy'] - 3, base['rsi_buy'], base['rsi_buy'] + 3]
    ses = [max(2, base['sma_exit'] - 1), base['sma_exit'], base['sma_exit'] + 1]
    pos = tot = 0
    for rl, rb, se in itertools.product(rls, rbs, ses):
        cf = dict(base); cf.update(rsi_len=rl, rsi_buy=float(rb), sma_exit=se)
        Tf = apply_filter(pf.all_trades(data, cf), reg, ddth, True, True)
        s = pf.stats(Tf); tot += 1; pos += (s['mean'] > 0 and s['wr'] >= 60)
    return round(pos / tot, 2)

print("\n" + "=" * 100)
print("ROBUSTNESS")
print("=" * 100)
pert = cperturb(-15.0)
print(f"perturb (entry-param plateau): {pert}  (>=0.8 = plateau)")

# perturb the FILTER threshold itself (is -15 a cliff?)
print("\nFilter dd-threshold sensitivity (sl100 OR dd<th):")
for th in [-10, -12, -13, -14, -15, -16, -17, -18, -20]:
    summary(f"  dd<{th}", apply_filter(T0, reg, th, True, True))

print("\nSlope lookback sensitivity (slope_lb days):")
for lb in [3, 5, 8, 10]:
    summary(f"  slope_lb={lb}", apply_filter(T0, build_reg(idx, lb), -15.0, True, True))

# ---- decompose: do BOTH legs matter? ----
print("\nDecompose legs:")
summary("  slope-only", apply_filter(T0, reg, -15.0, True, False))
summary("  dd-only(<-15)", apply_filter(T0, reg, -15.0, False, True))

# ---- holdout sign ----
print("\n" + "=" * 100)
print("HOLDOUT 2024-2026 (must be >0)")
print("=" * 100)
hW = W[W['xd'] >= np.datetime64('2024-01-01')]
print(f"holdout mean {pf.stats(hW)['mean']}  n={len(hW)}  WR={pf.stats(hW)['wr']}")
print("per_year (winner):", {k: round(float(v), 3) for k, v in r['py'].items()})

# ---- CONCENTRATION: is PnL driven by <=3 symbols? ----
print("\n" + "=" * 100)
print("CONCENTRATION (winner) — PnL by symbol")
print("=" * 100)
bysym = W.groupby('sym')['net'].agg(['sum', 'count']).sort_values('sum', ascending=False)
bysym['sum_pct'] = bysym['sum'] * 100
total_net = W['net'].sum()
print(f"total net (sum of trade net%, unweighted) = {total_net*100:.1f}")
print("Top contributors:")
print((bysym.head(8) * [1, 1, 1]).to_string())
top1 = bysym['sum'].iloc[0]
top3 = bysym['sum'].head(3).sum()
print(f"\nTop-1 symbol share of total net: {top1/total_net*100:.1f}%")
print(f"Top-3 symbol share of total net: {top3/total_net*100:.1f}%")
print(f"# symbols traded: {len(bysym)}  # profitable: {(bysym['sum']>0).sum()}")

# concentration of the IMPROVEMENT vs baseline (which trades does filter add/remove?)
print("\n--- What the filter changes vs baseline ---")
ids_base = set(zip(T0['ed'].astype('int64'), T0['xd'].astype('int64'), T0['sym']))
ids_w = set(zip(W['ed'].astype('int64'), W['xd'].astype('int64'), W['sym']))
removed = T0[[k not in ids_w for k in zip(T0['ed'].astype('int64'), T0['xd'].astype('int64'), T0['sym'])]]
print(f"baseline n={len(T0)} -> winner n={len(W)} (removed {len(T0)-len(W)} trades)")
print(f"removed trades: mean net% = {removed['net'].mean()*100:.3f}  WR={ (removed['net']>0).mean()*100:.1f}  sumnet%={removed['net'].sum()*100:.1f}")

# 2026 dependence: how much of the lift comes from 2026 capitulation bounce?
print("\n--- 2026 dependence (the dd<-15 capitulation re-add) ---")
for yr in [2023, 2024, 2025, 2026]:
    wy = W[pd.to_datetime(W['xd']).dt.year == yr]
    by = T0[pd.to_datetime(T0['xd']).dt.year == yr]
    print(f"  {yr}: winner n={len(wy):2d} mean={wy['net'].mean()*100 if len(wy) else 0:+.3f} "
          f"WR={(wy['net']>0).mean()*100 if len(wy) else 0:.0f} | baseline n={len(by):2d} mean={by['net'].mean()*100 if len(by) else 0:+.3f}")

# ---- DD honesty at lev (claim lev=1, but check lev sensitivity) ----
print("\n" + "=" * 100)
print("K / leverage sensitivity")
print("=" * 100)
for K in [3, 4, 5, 6, 8]:
    summary(f"  K={K}", W, K=K)
for lev in [1.0, 1.5, 2.0]:
    summary(f"  lev={lev}", W, lev=lev)
