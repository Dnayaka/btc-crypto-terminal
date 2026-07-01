import numpy as np, pandas as pd
import eng, itertools, multiprocessing

df = pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])

def get_sig(cf):
    o,h,l,c,r,e,a = eng.indicators(df, cf)
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
            if i > pb_watch_l or not intact_long[i]:
                pb_phase_l = 0
            elif pb_phase_l == 1:
                pb_peak_l = max(pb_peak_l, h[i])
                if (pb_peak_l - c[i]) / pb_peak_l * 100.0 >= pb_depth:
                    pb_phase_l = 2
            elif pb_phase_l == 2:
                if c[i] > pb_peak_l and c[i] > o[i] and ac[i] and af[i] and bo[i]:
                    pb_long[i] = True
                    pb_phase_l = 0
                    
        if short_raw[i] and intact_short[i]:
            pb_phase_s = 1
            pb_watch_s = i + pb_window
            pb_peak_s = l[i]
        elif pb_phase_s > 0:
            if i > pb_watch_s or not intact_short[i]:
                pb_phase_s = 0
            elif pb_phase_s == 1:
                pb_peak_s = min(pb_peak_s, l[i])
                if (c[i] - pb_peak_s) / pb_peak_s * 100.0 >= pb_depth:
                    pb_phase_s = 2
            elif pb_phase_s == 2:
                if c[i] < pb_peak_s and c[i] < o[i] and ac[i] and af[i] and bo[i]:
                    pb_short[i] = True
                    pb_phase_s = 0
    return pb_long, pb_short, atr_pct

base_cf = dict(eng.DEF)
base_cf.update(dict(
    ob=79.0, os=23.0, gap=3.0, cooldown=6,
    max_atr=1.0, atr_floor=0.2, body_min=0.3, long_emadist=1.5
))
pb_long, pb_short, atr_pct = get_sig(base_cf)
base_cf['add_long'] = pb_long
base_cf['add_short'] = pb_short

sl_opts = [1.8, 1.9, 2.0, 2.1, 2.2, 2.3]
tp_base_opts = [1.6, 1.7, 1.8, 1.9, 2.0, 2.1]
tp_gentle_opts = [2.0, 2.1, 2.15, 2.2, 2.3, 2.4, 2.5]
wall1_opts = [0.35, 0.40, 0.45]

import sys
# we want to beat v20: ret > 3422, WR > 64.6, DD <= 11.5 OR ret > 2600, WR > 68, DD <= 11.5
results = []
count = 0
for sl, tb, tg, w1 in itertools.product(sl_opts, tp_base_opts, tp_gentle_opts, wall1_opts):
    if tb >= tg: continue
    cf = dict(base_cf)
    cf['sl'] = sl
    cf['tp'] = np.where(atr_pct > w1, tg, tb)
    res, _ = eng.run(df, cf)
    if res['dd'] > 0:
        results.append({
            'sl': sl, 'tb': tb, 'tg': tg, 'w1': w1,
            'ret': res['ret'], 'dd': res['dd'], 'wr': res['wr'], 'calmar': res['calmar'], 'n': res['n']
        })
    count+=1
    if count % 100 == 0:
        print(f"Processed {count}...")

r_df = pd.DataFrame(results)
r_df.sort_values('ret', ascending=False, inplace=True)
print("Top Return configs (DD < 12):")
print(r_df[r_df['dd'] < 12].head(5))

r_df.sort_values('wr', ascending=False, inplace=True)
print("Top WR configs (DD < 12, Ret > 2000):")
print(r_df[(r_df['dd'] < 12) & (r_df['ret'] > 2000)].head(5))

r_df.sort_values('calmar', ascending=False, inplace=True)
print("Top Calmar configs:")
print(r_df.head(5))

# Target: Beat v20 (+3422, WR 64.6, DD 11.0)
beat_v20 = r_df[(r_df['ret'] > 3400) & (r_df['wr'] > 64.6) & (r_df['dd'] <= 11.5)]
print("Beats v20:")
print(beat_v20.head(5))

# High WR Balance (WR > 67, Ret > 2500)
high_wr = r_df[(r_df['wr'] > 67.0) & (r_df['ret'] > 2500) & (r_df['dd'] <= 11.5)]
print("High WR Balance:")
print(high_wr.head(5))

