import numpy as np, pandas as pd
import eng, itertools

df = pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])
dt = df['dt'].dt.year
idx_split = df[dt == 2024].index[0]
df_train = df.iloc[:idx_split].copy()
df_test = df.iloc[idx_split:].copy()
df_train.reset_index(drop=True, inplace=True)
df_test.reset_index(drop=True, inplace=True)

def calc_adx(h, l, c, length=14):
    up = h - np.roll(h, 1)
    dn = np.roll(l, 1) - l
    up[0] = 0; dn[0] = 0
    plusDM = np.where((up > dn) & (up > 0), up, 0)
    minusDM = np.where((dn > up) & (dn > 0), dn, 0)
    tr1 = h - l
    tr2 = np.abs(h - np.roll(c, 1))
    tr3 = np.abs(l - np.roll(c, 1))
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    tr[0] = 0
    tr_rma = eng.rma(tr, length)
    plus_rma = eng.rma(plusDM, length)
    minus_rma = eng.rma(minusDM, length)
    plusDI = 100 * plus_rma / np.where(tr_rma==0, 1, tr_rma)
    minusDI = 100 * minus_rma / np.where(tr_rma==0, 1, tr_rma)
    sumDI = plusDI + minusDI
    dx = 100 * np.abs(plusDI - minusDI) / np.where(sumDI==0, 1, sumDI)
    adx = eng.rma(dx, length)
    return adx

def get_sig_adv(df_period, cf):
    o,h,l,c,r,e,a = eng.indicators(df_period, cf)
    atr_pct = a/c*100.0
    rng = h-l
    body = np.where(rng>0, np.abs(c-o)/np.where(rng>0,rng,1), 0.0)
    
    vol = df_period['volume'].values
    vol_sma = pd.Series(vol).rolling(20).mean().values
    adx = calc_adx(h, l, c, 14)
    
    long_lvl = cf['ob']+cf['gap']; short_lvl = cf['os']-cf['gap']
    long_raw = (r>long_lvl) & (np.roll(r,1)<=long_lvl); long_raw[0]=False
    short_raw = (r<short_lvl) & (np.roll(r,1)>=short_lvl); short_raw[0]=False
    intact_long = c > e; intact_short = c < e
    ac = (cf['max_atr']<=0) | (atr_pct<=cf['max_atr'])
    af = (cf['atr_floor']<=0) | (atr_pct>=cf['atr_floor'])
    bo = (cf['body_min']<=0) | (body>=cf['body_min'])
    
    n = len(c)
    pb_long = np.zeros(n, dtype=bool)
    pb_short = np.zeros(n, dtype=bool)
    pb_phase_l = 0; pb_watch_l = 0; pb_peak_l = np.nan
    pb_phase_s = 0; pb_watch_s = 0; pb_peak_s = np.nan
    pb_win = 28; pb_dep = 1.0
    
    for i in range(n):
        if long_raw[i] and intact_long[i]:
            pb_phase_l = 1; pb_watch_l = i + pb_win; pb_peak_l = h[i]
        elif pb_phase_l > 0:
            if i > pb_watch_l or not intact_long[i]: pb_phase_l = 0
            elif pb_phase_l == 1:
                pb_peak_l = max(pb_peak_l, h[i])
                if (pb_peak_l - c[i]) / pb_peak_l * 100.0 >= pb_dep: pb_phase_l = 2
            elif pb_phase_l == 2:
                if c[i] > pb_peak_l and c[i] > o[i] and ac[i] and af[i] and bo[i]:
                    pb_long[i] = True; pb_phase_l = 0
        if short_raw[i] and intact_short[i]:
            pb_phase_s = 1; pb_watch_s = i + pb_win; pb_peak_s = l[i]
        elif pb_phase_s > 0:
            if i > pb_watch_s or not intact_short[i]: pb_phase_s = 0
            elif pb_phase_s == 1:
                pb_peak_s = min(pb_peak_s, l[i])
                if (c[i] - pb_peak_s) / pb_peak_s * 100.0 >= pb_dep: pb_phase_s = 2
            elif pb_phase_s == 2:
                if c[i] < pb_peak_s and c[i] < o[i] and ac[i] and af[i] and bo[i]:
                    pb_short[i] = True; pb_phase_s = 0
    return pb_long, pb_short, atr_pct, adx, vol, vol_sma

base_cf = dict(eng.DEF)
base_cf.update(dict(
    ob=79.0, os=23.0, gap=3.0, cooldown=6, sl=1.9,
    max_atr=1.0, atr_floor=0.2, body_min=0.3, long_emadist=1.5
))
pbl_tr, pbs_tr, atr_tr, adx_tr, vol_tr, volsma_tr = get_sig_adv(df_train, base_cf)

adx_thresh_opts = [0, 15, 20, 25, 30]
use_vol_opts = [False, True]

print("Starting V23 Advanced Filter Search (Train 2019-2023)...")
results = []
for adx_th, use_vol in itertools.product(adx_thresh_opts, use_vol_opts):
    cf = dict(base_cf)
    
    adx_ok = adx_tr > adx_th
    vol_ok = (vol_tr > volsma_tr) if use_vol else np.ones(len(vol_tr), dtype=bool)
    
    cf['add_long'] = pbl_tr & adx_ok & vol_ok
    cf['add_short'] = pbs_tr & adx_ok & vol_ok
    cf['tp'] = np.where(atr_tr > 0.40, 2.4, 2.0)
    
    res, _ = eng.run(df_train, cf)
    if res['dd'] > 0:
        results.append({
            'adx_th': adx_th, 'use_vol': use_vol,
            'ret': res['ret'], 'dd': res['dd'], 'wr': res['wr'], 'calmar': res['calmar'], 'n': res['n']
        })

r_df = pd.DataFrame(results)
r_df.sort_values('calmar', ascending=False, inplace=True)
print("\n--- TOP V23 CONFIGS IN TRAIN ---")
print(r_df.head(10))

# Evaluate on Full and Test
best = r_df.iloc[0]
if best['adx_th'] > 0 or best['use_vol']:
    print(f"\nWINNER: ADX > {best['adx_th']}, Use Vol = {best['use_vol']}")
    pbl_ts, pbs_ts, atr_ts, adx_ts, vol_ts, volsma_ts = get_sig_adv(df_test, base_cf)
    cf_ts = dict(base_cf)
    adx_ok_ts = adx_ts > best['adx_th']
    vol_ok_ts = (vol_ts > volsma_ts) if best['use_vol'] else np.ones(len(vol_ts), dtype=bool)
    cf_ts['add_long'] = pbl_ts & adx_ok_ts & vol_ok_ts
    cf_ts['add_short'] = pbs_ts & adx_ok_ts & vol_ok_ts
    cf_ts['tp'] = np.where(atr_ts > 0.40, 2.4, 2.0)
    res_ts, _ = eng.run(df_test, cf_ts)
    print("Test Holdout (2024-2026):", res_ts)
else:
    print("\nWINNER IS STILL BASELINE (ADX=0, VOL=False). NO EDGE GAINED.")

