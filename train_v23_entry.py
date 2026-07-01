import numpy as np, pandas as pd
import eng, itertools

df = pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])
dt = df['dt'].dt.year
idx_split = df[dt == 2024].index[0]
df_train = df.iloc[:idx_split].copy()
df_test = df.iloc[idx_split:].copy()
df_train.reset_index(drop=True, inplace=True)
df_test.reset_index(drop=True, inplace=True)

def run_train_entry(ob_opts, os_opts, body_opts, floor_opts):
    results = []
    base_cf = dict(eng.DEF)
    base_cf.update(dict(
        gap=3.0, cooldown=6, sl=1.9,
        max_atr=1.0, long_emadist=1.5
    ))
    # Note: eng.indicators is relatively slow if run inside the loop, 
    # but since OB/OS and others are used inside the signal generator,
    # we can precompute the indicators.
    o,h,l,c,r,e,a = eng.indicators(df_train, base_cf)
    atr_pct = a/c*100.0
    rng = h-l
    body = np.where(rng>0, np.abs(c-o)/np.where(rng>0,rng,1), 0.0)
    
    n = len(c)
    pb_window = 28
    pb_depth = 1.0
    
    tp_arr = np.where(atr_pct > 0.40, 2.4, 2.0)
    
    for ob, os, bmin, floor in itertools.product(ob_opts, os_opts, body_opts, floor_opts):
        # Prevent asymmetric extremes that are illogical (like ob=75 and os=19)
        # We can enforce symmetry roughly: ob + os should be ~100 +/- 4
        if abs((ob + os) - 100) > 4:
            continue
            
        long_lvl = ob + base_cf['gap']
        short_lvl = os - base_cf['gap']
        
        long_raw = (r>long_lvl) & (np.roll(r,1)<=long_lvl); long_raw[0]=False
        short_raw = (r<short_lvl) & (np.roll(r,1)>=short_lvl); short_raw[0]=False
        
        intact_long = c > e
        intact_short = c < e
        ac = (base_cf['max_atr']<=0) | (atr_pct<=base_cf['max_atr'])
        af = (floor<=0) | (atr_pct>=floor)
        bo = (bmin<=0) | (body>=bmin)
        
        pb_long = np.zeros(n, dtype=bool)
        pb_short = np.zeros(n, dtype=bool)
        pb_phase_l = 0; pb_watch_l = 0; pb_peak_l = np.nan
        pb_phase_s = 0; pb_watch_s = 0; pb_peak_s = np.nan
        
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
                        
        cf = dict(base_cf)
        cf['sl'] = 1.9
        cf['add_long'] = pb_long
        cf['add_short'] = pb_short
        cf['tp'] = tp_arr
        
        res, _ = eng.run(df_train, cf)
        if res['dd'] > 0:
            results.append({
                'ob': ob, 'os': os, 'bmin': bmin, 'floor': floor,
                'ret': res['ret'], 'dd': res['dd'], 'wr': res['wr'], 'calmar': res['calmar'], 'n': res['n']
            })
    return pd.DataFrame(results)

print("Running Entry Logic Grid Search on Train Set (2019-2023)...")
ob_opts = [73, 75, 77, 79, 81]
os_opts = [19, 21, 23, 25, 27]
body_opts = [0.2, 0.3, 0.4]
floor_opts = [0.15, 0.20, 0.25]

r_df = run_train_entry(ob_opts, os_opts, body_opts, floor_opts)
r_df.sort_values('ret', ascending=False, inplace=True)

print("\n--- TOP RETURN CONFIGS IN TRAIN ---")
print(r_df.head(5))

# We want a balanced one: WR > 64 and high return
balanced = r_df[(r_df['wr'] > 63.5) & (r_df['dd'] < 13)]
balanced.sort_values('ret', ascending=False, inplace=True)
print("\n--- TOP BALANCED CONFIGS (WR > 63.5, DD < 13) ---")
print(balanced.head(5))

