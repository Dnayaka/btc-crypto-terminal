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
    pb_phase_l = 0; pb_watch_l = 0; pb_peak_l = np.nan; peak_rsi_l = np.nan
    pb_phase_s = 0; pb_watch_s = 0; pb_peak_s = np.nan; peak_rsi_s = np.nan
    pb_win = 28; pb_dep = 1.0
    
    # Let's also store the peak RSI for analysis
    entry_peak_rsi = np.zeros(n)
    
    for i in range(n):
        if long_raw[i] and intact_long[i]:
            pb_phase_l = 1; pb_watch_l = i + pb_win; pb_peak_l = h[i]; peak_rsi_l = r[i]
        elif pb_phase_l > 0:
            if i > pb_watch_l or not intact_long[i]: pb_phase_l = 0
            elif pb_phase_l == 1:
                if h[i] > pb_peak_l:
                    pb_peak_l = h[i]
                    peak_rsi_l = r[i]
                if (pb_peak_l - c[i]) / pb_peak_l * 100.0 >= pb_dep: pb_phase_l = 2
            elif pb_phase_l == 2:
                if c[i] > pb_peak_l and c[i] > o[i] and ac[i] and af[i] and bo[i]:
                    pb_long[i] = True; pb_phase_l = 0
                    entry_peak_rsi[i] = peak_rsi_l
                    
        if short_raw[i] and intact_short[i]:
            pb_phase_s = 1; pb_watch_s = i + pb_win; pb_peak_s = l[i]; peak_rsi_s = r[i]
        elif pb_phase_s > 0:
            if i > pb_watch_s or not intact_short[i]: pb_phase_s = 0
            elif pb_phase_s == 1:
                if l[i] < pb_peak_s:
                    pb_peak_s = l[i]
                    peak_rsi_s = r[i]
                if (c[i] - pb_peak_s) / pb_peak_s * 100.0 >= pb_dep: pb_phase_s = 2
            elif pb_phase_s == 2:
                if c[i] < pb_peak_s and c[i] < o[i] and ac[i] and af[i] and bo[i]:
                    pb_short[i] = True; pb_phase_s = 0
                    entry_peak_rsi[i] = peak_rsi_s
                    
    hours = df_period['dt'].dt.hour.values
    us_session = (hours >= 12) & (hours <= 17)
    pb_long = pb_long & (~us_session)
    pb_short = pb_short & (~us_session)
        
    return pb_long, pb_short, atr_pct, e, entry_peak_rsi

cf = dict(eng.DEF)
cf.update(dict(
    ob=79.0, os=23.0, gap=3.0, cooldown=6, sl=1.9,
    max_atr=1.0, atr_floor=0.2, body_min=0.3, long_emadist=1.5
))

pbl, pbs, atr, ema, entry_rsi = get_sig_v23(df, cf)
tp_arr = np.where(atr > 0.40, 2.4, 2.0)
sl = 1.9

# Custom backtest to extract trade info
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
                trades.append({'res': -1, 'type':'L', 'dur': i-entry_idx, 'peak_rsi': entry_rsi[entry_idx], 'ema800_dist': dist_800})
                pos = 0; cooldown_cnt = cf['cooldown']
            elif h[i] >= tp_p:
                trades.append({'res': 1, 'type':'L'})
                pos = 0; cooldown_cnt = cf['cooldown']
        elif pos == -1:
            if h[i] >= sl_p:
                dist_800 = (ema800[entry_idx] - c[entry_idx]) / ema800[entry_idx] * 100
                trades.append({'res': -1, 'type':'S', 'dur': i-entry_idx, 'peak_rsi': entry_rsi[entry_idx], 'ema800_dist': dist_800})
                pos = 0; cooldown_cnt = cf['cooldown']
            elif l[i] <= tp_p:
                trades.append({'res': 1, 'type':'S'})
                pos = 0; cooldown_cnt = cf['cooldown']

tdf = pd.DataFrame(trades)
losses = tdf[tdf['res'] == -1]
print("V23 Total Losses Analyzed:", len(losses))

print("\n--- MACRO TREND ANALYSIS (EMA 800 Distance) ---")
print("We assume trading WITH macro trend if EMA 800 dist > 0.")
against_macro = losses[losses['ema800_dist'] < 0]
print(f"Losses against 4H macro trend: {len(against_macro)} ({len(against_macro)/len(losses)*100:.1f}%)")

print("\n--- EXHAUSTION ANALYSIS (Peak RSI) ---")
extreme_longs = losses[(losses['type'] == 'L') & (losses['peak_rsi'] > 90)]
extreme_shorts = losses[(losses['type'] == 'S') & (losses['peak_rsi'] < 10)]
exhausted = len(extreme_longs) + len(extreme_shorts)
print(f"Losses from Extreme Exhaustion (RSI > 90 or < 10): {exhausted} ({exhausted/len(losses)*100:.1f}%)")
print("Average Peak RSI on Long Losses:", losses[losses['type']=='L']['peak_rsi'].mean())

print("\n--- CONSECUTIVE WHIPSAWS ---")
print("Shortest loss durations (Flash Crashes remaining):")
flash = losses[losses['dur'] <= 4]
print(f"Flash crashes (duration <= 4 bars): {len(flash)} ({len(flash)/len(losses)*100:.1f}%)")

