import numpy as np, pandas as pd
import eng

df = pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])

cf = dict(eng.DEF)
cf.update(dict(
    ob=79.0, os=23.0, gap=3.0, sl=2.0, cooldown=6,
    max_atr=1.0, atr_floor=0.2, body_min=0.3, long_emadist=1.5
))

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

cf['add_long'] = pb_long
cf['add_short'] = pb_short
cf['tp'] = np.where(atr_pct > 0.40, 2.2, 1.8)

res, t = eng.run(df, cf)
print("v22 Hybrid:", res)
