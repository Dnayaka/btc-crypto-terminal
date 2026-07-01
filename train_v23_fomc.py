import numpy as np, pandas as pd
import eng

df = pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])
dt = df['dt'].dt.year
idx_split = df[dt == 2024].index[0]
df_train = df.iloc[:idx_split].copy()
df_test = df.iloc[idx_split:].copy()
df_train.reset_index(drop=True, inplace=True)
df_test.reset_index(drop=True, inplace=True)

def get_sig_fomc(df_period, cf, filter_type='none'):
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
                    
    # Standard v23 US Session Filter
    hours = df_period['dt'].dt.hour.values
    us_session = (hours >= 12) & (hours <= 17)
    pb_long = pb_long & (~us_session)
    pb_short = pb_short & (~us_session)
    
    # FOMC / Wednesday Filter
    days = df_period['dt'].dt.dayofweek.values
    if filter_type == 'fomc':
        # Wednesday 17:00 - 21:00 UTC
        fomc = (days == 2) & (hours >= 17) & (hours <= 21)
        pb_long = pb_long & (~fomc)
        pb_short = pb_short & (~fomc)
    elif filter_type == 'full_wed':
        # Full Wednesday
        wed = (days == 2)
        pb_long = pb_long & (~wed)
        pb_short = pb_short & (~wed)
        
    return pb_long, pb_short, atr_pct

cf = dict(eng.DEF)
cf.update(dict(
    ob=79.0, os=23.0, gap=3.0, cooldown=6, sl=1.9,
    max_atr=1.0, atr_floor=0.2, body_min=0.3, long_emadist=1.5
))

def evaluate(filter_type):
    print(f"\n--- FILTER: {filter_type.upper()} ---")
    
    pbl, pbs, atr_pct = get_sig_fomc(df_train, cf, filter_type)
    cf['add_long'] = pbl
    cf['add_short'] = pbs
    cf['tp'] = np.where(atr_pct > 0.40, 2.4, 2.0)
    res_tr, _ = eng.run(df_train, cf)
    
    pbl_ts, pbs_ts, atr_pct_ts = get_sig_fomc(df_test, cf, filter_type)
    cf_ts = dict(cf)
    cf_ts['add_long'] = pbl_ts
    cf_ts['add_short'] = pbs_ts
    cf_ts['tp'] = np.where(atr_pct_ts > 0.40, 2.4, 2.0)
    res_ts, _ = eng.run(df_test, cf_ts)
    
    pbl_f, pbs_f, atr_pct_f = get_sig_fomc(df, cf, filter_type)
    cf_f = dict(cf)
    cf_f['add_long'] = pbl_f
    cf_f['add_short'] = pbs_f
    cf_f['tp'] = np.where(atr_pct_f > 0.40, 2.4, 2.0)
    res_f, _ = eng.run(df, cf_f)
    
    print(f"TRAIN (2019-2023): Ret={res_tr['ret']:.1f}%, DD={res_tr['dd']:.2f}%, WR={res_tr['wr']:.2f}%, Trades={res_tr['n']}")
    print(f"TEST  (2024-2026): Ret={res_ts['ret']:.1f}%, DD={res_ts['dd']:.2f}%, WR={res_ts['wr']:.2f}%, Trades={res_ts['n']}")
    print(f"FULL  (2019-2026): Ret={res_f['ret']:.1f}%, DD={res_f['dd']:.2f}%, WR={res_f['wr']:.2f}%, Trades={res_f['n']}")

evaluate('none')
evaluate('fomc')
evaluate('full_wed')

