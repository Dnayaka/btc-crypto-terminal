import numpy as np, pandas as pd
import eng

# Load full data
df = pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])

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
    return pb_long, pb_short, atr_pct, e

cf = dict(eng.DEF)
cf.update(dict(
    ob=79.0, os=23.0, gap=3.0, cooldown=6, sl=1.9,
    max_atr=1.0, atr_floor=0.2, body_min=0.3, long_emadist=1.5
))

pbl, pbs, atr, ema = get_sig(df, cf)
cf['add_long'] = pbl
cf['add_short'] = pbs
cf['tp'] = np.where(atr > 0.40, 2.4, 2.0)

# We need to extract trades. eng.run() returns stats, but let's hack it or write a simple sim
def get_trades(df_p, add_l, add_s, tp_arr, sl):
    o = df_p['open'].values
    h = df_p['high'].values
    l = df_p['low'].values
    c = df_p['close'].values
    dt = df_p['dt'].dt
    
    trades = []
    pos = 0 # 1 long, -1 short
    entry_p = 0.0
    entry_idx = 0
    tp_p = 0.0
    sl_p = 0.0
    cooldown_cnt = 0
    
    for i in range(len(c)):
        if cooldown_cnt > 0:
            cooldown_cnt -= 1
            continue
            
        if pos == 0:
            if add_l[i]:
                pos = 1
                entry_p = c[i]
                entry_idx = i
                tp_p = entry_p * (1.0 + tp_arr[i]/100.0)
                sl_p = entry_p * (1.0 - sl/100.0)
            elif add_s[i]:
                pos = -1
                entry_p = c[i]
                entry_idx = i
                tp_p = entry_p * (1.0 - tp_arr[i]/100.0)
                sl_p = entry_p * (1.0 + sl/100.0)
        else:
            if pos == 1:
                if l[i] <= sl_p:
                    trades.append({'type':'L','res':-1,'dur':i-entry_idx,'entry_dt':df_p['dt'].iloc[entry_idx]})
                    pos = 0; cooldown_cnt = cf['cooldown']
                elif h[i] >= tp_p:
                    trades.append({'type':'L','res':1,'dur':i-entry_idx,'entry_dt':df_p['dt'].iloc[entry_idx]})
                    pos = 0; cooldown_cnt = cf['cooldown']
            elif pos == -1:
                if h[i] >= sl_p:
                    trades.append({'type':'S','res':-1,'dur':i-entry_idx,'entry_dt':df_p['dt'].iloc[entry_idx]})
                    pos = 0; cooldown_cnt = cf['cooldown']
                elif l[i] <= tp_p:
                    trades.append({'type':'S','res':1,'dur':i-entry_idx,'entry_dt':df_p['dt'].iloc[entry_idx]})
                    pos = 0; cooldown_cnt = cf['cooldown']
    return pd.DataFrame(trades)

tdf = get_trades(df, pbl, pbs, cf['tp'], cf['sl'])
tdf['hour'] = tdf['entry_dt'].dt.hour
tdf['day'] = tdf['entry_dt'].dt.dayofweek # 0=Mon, 6=Sun

losses = tdf[tdf['res'] == -1]
wins = tdf[tdf['res'] == 1]

print("TOTAL TRADES:", len(tdf))
print("LOSSES:", len(losses))

print("\n--- LOSSES BY HOUR (UTC) ---")
print(losses['hour'].value_counts().sort_index().head(24))

print("\n--- LOSSES BY DAY OF WEEK (0=Mon, 6=Sun) ---")
print(losses['day'].value_counts().sort_index())

print("\n--- DURATIONS (Number of 15m Bars) ---")
print("Average Loss Duration:", losses['dur'].mean())
print("Average Win Duration:", wins['dur'].mean())

print("\n--- FLASH CRASHES (SL Hit in < 4 bars / 1 hour) ---")
flash = losses[losses['dur'] <= 4]
print(f"Number of rapid stoplosses: {len(flash)} ({len(flash)/len(losses)*100:.1f}%)")

