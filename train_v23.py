import numpy as np, pandas as pd
import eng, itertools

df = pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])
dt = df['dt'].dt.year
idx_split = df[dt == 2024].index[0]
df_train = df.iloc[:idx_split].copy()
df_test = df.iloc[idx_split:].copy()
df_train.reset_index(drop=True, inplace=True)
df_test.reset_index(drop=True, inplace=True)

def get_sig(df_period, cf):
    o,h,l,c,r,e,a = eng.indicators(df_period, cf)
    atr_pct = a/c*100.0
    rng = h-l
    body = np.where(rng>0, np.abs(c-o)/np.where(rng>0,rng,1), 0.0)

    long_lvl = cf['ob']+cf['gap']; short_lvl = cf['os']-cf['gap']
    long_raw = (r>long_lvl) & (np.roll(r,1)<=long_lvl); long_raw[0]=False
    short_raw = (r<short_lvl) & (np.roll(r,1)>=short_lvl); short_raw[0]=False

    intact_long = c > e
    intact_short = c < e
    ac = (cf['max_atr']<=0) | (atr_pct<=cf['max_atr'])
    af = (cf['atr_floor']<=0) | (atr_pct>=cf['atr_floor'])
    bo = (cf['body_min']<=0) | (body>=cf['body_min'])

    n = len(c)
    pb_long = np.zeros(n, dtype=bool)
    pb_short = np.zeros(n, dtype=bool)
    pb_phase_l = 0; pb_watch_l = 0; pb_peak_l = np.nan
    pb_phase_s = 0; pb_watch_s = 0; pb_peak_s = np.nan
    pb_window = 28; pb_depth = 1.0

    for i in range(n):
        if long_raw[i] and intact_long[i]:
            pb_phase_l = 1
            pb_watch_l = i + pb_window
            pb_peak_l = h[i]
        elif pb_phase_l > 0:
            if i > pb_watch_l or not intact_long[i]: pb_phase_l = 0
            elif pb_phase_l == 1:
                pb_peak_l = max(pb_peak_l, h[i])
                if (pb_peak_l - c[i]) / pb_peak_l * 100.0 >= pb_depth: pb_phase_l = 2
            elif pb_phase_l == 2:
                if c[i] > pb_peak_l and c[i] > o[i] and ac[i] and af[i] and bo[i]:
                    pb_long[i] = True; pb_phase_l = 0
                    
        if short_raw[i] and intact_short[i]:
            pb_phase_s = 1
            pb_watch_s = i + pb_window
            pb_peak_s = l[i]
        elif pb_phase_s > 0:
            if i > pb_watch_s or not intact_short[i]: pb_phase_s = 0
            elif pb_phase_s == 1:
                pb_peak_s = min(pb_peak_s, l[i])
                if (c[i] - pb_peak_s) / pb_peak_s * 100.0 >= pb_depth: pb_phase_s = 2
            elif pb_phase_s == 2:
                if c[i] < pb_peak_s and c[i] < o[i] and ac[i] and af[i] and bo[i]:
                    pb_short[i] = True; pb_phase_s = 0
    return pb_long, pb_short, atr_pct

base_cf = dict(eng.DEF)
base_cf.update(dict(
    ob=79.0, os=23.0, gap=3.0, cooldown=6,
    max_atr=1.0, atr_floor=0.2, body_min=0.3, long_emadist=1.5
))

# Precompute signals for TRAIN
pb_l_tr, pb_s_tr, atr_tr = get_sig(df_train, base_cf)
# Precompute signals for TEST
pb_l_ts, pb_s_ts, atr_ts = get_sig(df_test, base_cf)
# Precompute signals for FULL
pb_l_f, pb_s_f, atr_f = get_sig(df, base_cf)

sl_opts = [1.8, 1.9, 2.0, 2.1, 2.2]
tp_base_opts = [1.6, 1.8, 2.0, 2.2]
tp_gentle_opts = [2.0, 2.2, 2.4, 2.6, 2.8]
wall1_opts = [0.35, 0.40, 0.45]

print("Starting Train Search (2019-2023)...")
train_results = []
for sl, tb, tg, w1 in itertools.product(sl_opts, tp_base_opts, tp_gentle_opts, wall1_opts):
    if tb >= tg: continue
    cf = dict(base_cf)
    cf['sl'] = sl
    cf['add_long'] = pb_l_tr
    cf['add_short'] = pb_s_tr
    cf['tp'] = np.where(atr_tr > w1, tg, tb)
    res, _ = eng.run(df_train, cf)
    if res['dd'] > 0 and res['ret'] > 500:
        train_results.append({
            'sl': sl, 'tb': tb, 'tg': tg, 'w1': w1,
            'ret': res['ret'], 'dd': res['dd'], 'wr': res['wr'], 'calmar': res['calmar'], 'n': res['n']
        })

r_tr = pd.DataFrame(train_results)
r_tr.sort_values('calmar', ascending=False, inplace=True)

print("\n--- TOP 3 CALMAR CONFIGS IN TRAIN (2019-2023) ---")
print(r_tr.head(3))

r_tr.sort_values('ret', ascending=False, inplace=True)
print("\n--- TOP 3 RETURN CONFIGS IN TRAIN (2019-2023, DD < 13) ---")
top_ret = r_tr[r_tr['dd']<13].head(3)
print(top_ret)

best_cfg = r_tr[r_tr['dd']<13].iloc[0]
bsl, btb, btg, bw1 = best_cfg['sl'], best_cfg['tb'], best_cfg['tg'], best_cfg['w1']
print(f"\nSELECTED TRUE-TRAIN BEST: SL={bsl} TB={btb} TG={btg} Wall={bw1}")

print("\n--- EVALUATING SELECTED CONFIG ON HOLDOUT (2024-2026) ---")
cf_test = dict(base_cf)
cf_test['sl'] = bsl
cf_test['add_long'] = pb_l_ts
cf_test['add_short'] = pb_s_ts
cf_test['tp'] = np.where(atr_ts > bw1, btg, btb)
res_test, _ = eng.run(df_test, cf_test)
print(res_test)

print("\n--- EVALUATING SELECTED CONFIG ON FULL PERIOD (2019-2026) ---")
cf_full = dict(base_cf)
cf_full['sl'] = bsl
cf_full['add_long'] = pb_l_f
cf_full['add_short'] = pb_s_f
cf_full['tp'] = np.where(atr_f > bw1, btg, btb)
res_full, t_full = eng.run(df, cf_full)
print(res_full)
yrs = eng.per_year(df, t_full)
print("Per-Year:", yrs)
