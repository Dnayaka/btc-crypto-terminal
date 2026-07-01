import numpy as np, pandas as pd
import eng

df = pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])

def get_sig_v23(df_period, cf):
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
                    
    hours = df_period['dt'].dt.hour.values
    us_session = (hours >= 12) & (hours <= 17)
    pb_long = pb_long & (~us_session)
    pb_short = pb_short & (~us_session)
        
    return pb_long, pb_short, atr_pct

cf = dict(eng.DEF)
cf.update(dict(
    ob=79.0, os=23.0, gap=3.0, cooldown=6, sl=1.9,
    max_atr=1.0, atr_floor=0.2, body_min=0.3, long_emadist=1.5
))

pbl, pbs, atr = get_sig_v23(df, cf)
tp_arr = np.where(atr > 0.40, 2.4, 2.0)
sl = 1.9

o = df['open'].values
h = df['high'].values
l = df['low'].values
c = df['close'].values
ema800 = pd.Series(c).ewm(span=800, adjust=False).mean().values

trades = []
pos = 0 
entry_idx = 0
tp_p = 0.0
sl_p = 0.0
cooldown_cnt = 0

for i in range(len(c)):
    if cooldown_cnt > 0:
        cooldown_cnt -= 1
        continue
        
    if pos == 0:
        if pbl[i]:
            pos = 1; entry_idx = i
            tp_p = c[i] * (1.0 + tp_arr[i]/100.0)
            sl_p = c[i] * (1.0 - sl/100.0)
        elif pbs[i]:
            pos = -1; entry_idx = i
            tp_p = c[i] * (1.0 - tp_arr[i]/100.0)
            sl_p = c[i] * (1.0 + sl/100.0)
    else:
        if pos == 1:
            if l[i] <= sl_p:
                dist_800 = (c[entry_idx] - ema800[entry_idx]) / ema800[entry_idx] * 100
                dt_entry = df['dt'].iloc[entry_idx]
                trades.append({'res': -1, 'type':'L', 'ema800_dist': dist_800, 'dt': dt_entry})
                pos = 0; cooldown_cnt = cf['cooldown']
            elif h[i] >= tp_p:
                dist_800 = (c[entry_idx] - ema800[entry_idx]) / ema800[entry_idx] * 100
                dt_entry = df['dt'].iloc[entry_idx]
                trades.append({'res': 1, 'type':'L', 'ema800_dist': dist_800, 'dt': dt_entry})
                pos = 0; cooldown_cnt = cf['cooldown']
        elif pos == -1:
            if h[i] >= sl_p:
                dist_800 = (ema800[entry_idx] - c[entry_idx]) / ema800[entry_idx] * 100
                dt_entry = df['dt'].iloc[entry_idx]
                trades.append({'res': -1, 'type':'S', 'ema800_dist': dist_800, 'dt': dt_entry})
                pos = 0; cooldown_cnt = cf['cooldown']
            elif l[i] <= tp_p:
                dist_800 = (ema800[entry_idx] - c[entry_idx]) / ema800[entry_idx] * 100
                dt_entry = df['dt'].iloc[entry_idx]
                trades.append({'res': 1, 'type':'S', 'ema800_dist': dist_800, 'dt': dt_entry})
                pos = 0; cooldown_cnt = cf['cooldown']

tdf = pd.DataFrame(trades)

total_trades = len(tdf)
total_won = len(tdf[tdf['res'] == 1])
total_lost = len(tdf[tdf['res'] == -1])

# Trend direction
tdf['with_trend'] = tdf['ema800_dist'] > 0
total_with_trend = len(tdf[tdf['with_trend'] == True])
total_against_trend = len(tdf[tdf['with_trend'] == False])

won_with_trend = len(tdf[(tdf['with_trend'] == True) & (tdf['res'] == 1)])
lost_with_trend = len(tdf[(tdf['with_trend'] == True) & (tdf['res'] == -1)])
won_against = len(tdf[(tdf['with_trend'] == False) & (tdf['res'] == 1)])
lost_against = len(tdf[(tdf['with_trend'] == False) & (tdf['res'] == -1)])

# Macro News Approximation (FOMC typically Wed 18:00-19:00 UTC)
# And high-impact news days: Tuesday-Thursday 17:00-19:00 (since 12-17 is already skipped)
tdf['is_fomc'] = (tdf['dt'].dt.dayofweek == 2) & (tdf['dt'].dt.hour.isin([18, 19, 20]))
tdf['is_news_spillover'] = (tdf['dt'].dt.dayofweek.isin([1,2,3])) & (tdf['dt'].dt.hour.isin([17, 18, 19]))

fomc_trades = tdf[tdf['is_fomc']]
fomc_won = len(fomc_trades[fomc_trades['res'] == 1])
fomc_lost = len(fomc_trades[fomc_trades['res'] == -1])

news_trades = tdf[tdf['is_news_spillover']]
news_won = len(news_trades[news_trades['res'] == 1])
news_lost = len(news_trades[news_trades['res'] == -1])

print(f"Total Transaksi (V23): {total_trades}")
print(f"Menang (TP): {total_won} ({(total_won/total_trades*100):.1f}%)")
print(f"Kalah (SL): {total_lost} ({(total_lost/total_trades*100):.1f}%)")
print("-" * 30)
print(f"Sejalan Arus (Dengan Tren 4H): {total_with_trend}")
print(f"  - Menang: {won_with_trend}")
print(f"  - Kalah: {lost_with_trend}")
print(f"Lawan Arus (Melawan Tren 4H): {total_against_trend}")
print(f"  - Menang: {won_against}")
print(f"  - Kalah: {lost_against}")
print("-" * 30)
print(f"FOMC / The Fed (Rabu Malam UTC): {len(fomc_trades)} trades")
print(f"  - Menang: {fomc_won}")
print(f"  - Kalah: {fomc_lost}")
print(f"News Spillover (Selasa-Kamis pasca buka sesi AS): {len(news_trades)} trades")
print(f"  - Menang: {news_won}")
print(f"  - Kalah: {news_lost}")

