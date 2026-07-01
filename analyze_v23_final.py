import numpy as np, pandas as pd
import eng

df = pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])

def get_sig_fomc(df_period, cf):
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
    days = df_period['dt'].dt.dayofweek.values
    
    us_session = (hours >= 12) & (hours <= 17)
    fomc = (days == 2) & (hours >= 17) & (hours <= 21)
    
    pb_long = pb_long & (~us_session) & (~fomc)
    pb_short = pb_short & (~us_session) & (~fomc)
        
    return pb_long, pb_short, atr_pct

cf = dict(eng.DEF)
cf.update(dict(
    ob=79.0, os=23.0, gap=3.0, cooldown=6, sl=1.9,
    max_atr=1.0, atr_floor=0.2, body_min=0.3, long_emadist=1.5
))

pbl, pbs, atr_pct = get_sig_fomc(df, cf)
cf['add_long'] = pbl
cf['add_short'] = pbs
cf['tp'] = np.where(atr_pct > 0.40, 2.4, 2.0)

res, tdf = eng.run(df, cf)

losses = tdf[tdf['net'] < 0].copy()
wins = tdf[tdf['net'] > 0].copy()

losses['dur'] = losses['exit_bar'] - losses['entry_bar']
wins['dur'] = wins['exit_bar'] - wins['entry_bar']

c = df['close'].values
ema200 = pd.Series(c).ewm(span=200, adjust=False).mean().values

def get_ema_slope(bar):
    if bar >= 50:
        return abs(ema200[bar] - ema200[bar-50]) / ema200[bar-50] * 100
    return 0.0

losses['ema_slope'] = losses['entry_bar'].apply(get_ema_slope)
wins['ema_slope'] = wins['entry_bar'].apply(get_ema_slope)
losses['month'] = losses['entry_bar'].apply(lambda x: df['dt'].iloc[x].month)

print(f"Total True Losses Analyzed: {len(losses)}")
print(f"Total True Wins Analyzed: {len(wins)}")

print("\n--- CHOPPINESS (EMA Slope Analysis) ---")
print(f"Average EMA200 50-bar slope on WINS: {wins['ema_slope'].mean():.3f}%")
print(f"Average EMA200 50-bar slope on LOSSES: {losses['ema_slope'].mean():.3f}%")
flat_losses = losses[losses['ema_slope'] < 0.2]
print(f"Losses in flat/choppy markets (slope < 0.2%): {len(flat_losses)} ({len(flat_losses)/len(losses)*100:.1f}%)")

print("\n--- MAX FAVORABLE EXCURSION (Did they almost win?) ---")
almost_won = losses[losses['mfe'] >= 1.5]
print(f"Losses that reached >1.5% profit before reversing to SL: {len(almost_won)} ({len(almost_won)/len(losses)*100:.1f}%)")
print(f"Average MFE on losses: {losses['mfe'].mean():.2f}%")

print("\n--- CONSECUTIVE LOSSES (Are they clustered?) ---")
tdf_sorted = tdf.sort_values('entry_bar')
tdf_sorted['prev_net'] = tdf_sorted['net'].shift(1)
consecutive = tdf_sorted[(tdf_sorted['net'] < 0) & (tdf_sorted['prev_net'] < 0)]
print(f"Losses that occurred immediately after a previous loss: {len(consecutive)} ({len(consecutive)/len(losses)*100:.1f}%)")

print("\n--- LOSSES BY MONTH (Seasonality) ---")
print(losses['month'].value_counts().sort_index())
