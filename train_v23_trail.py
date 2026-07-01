import numpy as np, pandas as pd
import eng, itertools

df = pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])
dt = df['dt'].dt.year
idx_split = df[dt == 2024].index[0]
df_train = df.iloc[:idx_split].copy()

def get_sig(df_period, cf):
    o,h,l,c,r,e,a = eng.indicators(df_period, cf)
    atr_pct = a/c*100.0
    rng = h-l
    body = np.where(rng>0, np.abs(c-o)/np.where(rng>0,rng,1), 0.0)
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
    pb_window = 28; pb_depth = 1.0
    for i in range(n):
        if long_raw[i] and intact_long[i]:
            pb_phase_l = 1; pb_watch_l = i + pb_window; pb_peak_l = h[i]
        elif pb_phase_l > 0:
            if i > pb_watch_l or not intact_long[i]: pb_phase_l = 0
            elif pb_phase_l == 1:
                pb_peak_l = max(pb_peak_l, h[i])
                if (pb_peak_l - c[i]) / pb_peak_l * 100.0 >= pb_depth: pb_phase_l = 2
            elif pb_phase_l == 2:
                if c[i] > pb_peak_l and c[i] > o[i] and ac[i] and af[i] and bo[i]:
                    pb_long[i] = True; pb_phase_l = 0
        if short_raw[i] and intact_short[i]:
            pb_phase_s = 1; pb_watch_s = i + pb_window; pb_peak_s = l[i]
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
    ob=79.0, os=23.0, gap=3.0, cooldown=6, sl=1.9,
    max_atr=1.0, atr_floor=0.2, body_min=0.3, long_emadist=1.5
))
pb_l_tr, pb_s_tr, atr_tr = get_sig(df_train, base_cf)

tmult_opts = [1.5, 2.0, 2.5]
tact_opts = [1.5, 2.0, 2.5]
tmin = 0.5
tmax = 2.0

print("Starting Train Search Pure Runner (TP=0)...")
train_results = []
for tmult, tact in itertools.product(tmult_opts, tact_opts):
    cf = dict(base_cf)
    cf['add_long'] = pb_l_tr
    cf['add_short'] = pb_s_tr
    cf['tp'] = 0.0 # pure runner
    cf['use_trail'] = True
    cf['trail_mult'] = tmult
    cf['trail_act'] = tact
    cf['trail_min'] = tmin
    cf['trail_max'] = tmax
    
    res, _ = eng.run(df_train, cf)
    if res['dd'] > 0:
        train_results.append({
            'tmult': tmult, 'tact': tact,
            'ret': res['ret'], 'dd': res['dd'], 'wr': res['wr'], 'calmar': res['calmar'], 'n': res['n']
        })

r_tr = pd.DataFrame(train_results)
r_tr.sort_values('ret', ascending=False, inplace=True)
print("\n--- TOP PURE RUNNER CONFIGS IN TRAIN ---")
print(r_tr.head(5))

# Also search TP + trailing stop combo
print("\nStarting Train Search Combo (TP + Trailing)...")
combo_results = []
for tp, tact in itertools.product([2.4, 2.6, 2.8, 3.0, 4.0], [1.5, 2.0, 2.5]):
    if tp <= tact: continue
    cf = dict(base_cf)
    cf['add_long'] = pb_l_tr
    cf['add_short'] = pb_s_tr
    cf['tp'] = tp
    cf['use_trail'] = True
    cf['trail_mult'] = 2.0
    cf['trail_act'] = tact
    cf['trail_min'] = 0.5
    cf['trail_max'] = 2.0
    
    res, _ = eng.run(df_train, cf)
    if res['dd'] > 0:
        combo_results.append({
            'tp': tp, 'tact': tact,
            'ret': res['ret'], 'dd': res['dd'], 'wr': res['wr'], 'calmar': res['calmar']
        })

r_combo = pd.DataFrame(combo_results)
r_combo.sort_values('ret', ascending=False, inplace=True)
print(r_combo.head(5))
