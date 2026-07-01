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
    max_atr=1.0, atr_floor=0.2, body_min=0.3, long_emadist=0.0
))

pbl, pbs, atr_pct = get_sig_fomc(df, cf)
tp_arr = np.where(atr_pct > 0.40, 2.4, 2.0)
sl = 1.9
fee = 0.04
slippage = 0.05 # Add massive 0.05% slippage on EVERY entry and exit!

o = df['open'].values
h = df['high'].values
l = df['low'].values
c = df['close'].values

def simulate_reentry_stress(reentry_drop=None, risk_per_unit_pct=1.0):
    trades = []
    pos = 0 
    entry_idx = 0
    tp_p = 0.0
    sl_p = 0.0
    reentry_p = 0.0
    units = 0
    avg_px = 0.0
    cooldown_cnt = 0
    
    for i in range(len(c)):
        if cooldown_cnt > 0:
            cooldown_cnt -= 1
            continue
            
        if pos == 0:
            if pbl[i]:
                pos = 1; entry_idx = i; units = 1
                avg_px = c[i]
                tp_p = avg_px * (1.0 + tp_arr[i]/100.0)
                sl_p = avg_px * (1.0 - sl/100.0)
                if reentry_drop:
                    reentry_p = avg_px * (1.0 - reentry_drop/100.0)
            elif pbs[i]:
                pos = -1; entry_idx = i; units = 1
                avg_px = c[i]
                tp_p = avg_px * (1.0 - tp_arr[i]/100.0)
                sl_p = avg_px * (1.0 + sl/100.0)
                if reentry_drop:
                    reentry_p = avg_px * (1.0 + reentry_drop/100.0)
        else:
            if pos == 1:
                if reentry_drop and units == 1 and l[i] <= reentry_p:
                    units = 2
                    avg_px = (avg_px + reentry_p) / 2.0
                    tp_p = avg_px * (1.0 + tp_arr[entry_idx]/100.0)
                    sl_p = avg_px * (1.0 - sl/100.0)
                
                if h[i] >= tp_p:
                    ret = (tp_arr[entry_idx]/100.0 - 2*fee/100.0 - 2*slippage/100.0)
                    trades.append({'res': 1, 'ret': ret, 'units': units})
                    pos = 0; cooldown_cnt = cf['cooldown']
                elif l[i] <= sl_p:
                    ret = (-sl/100.0 - 2*fee/100.0 - 2*slippage/100.0)
                    trades.append({'res': -1, 'ret': ret, 'units': units})
                    pos = 0; cooldown_cnt = cf['cooldown']
                    
            elif pos == -1:
                if reentry_drop and units == 1 and h[i] >= reentry_p:
                    units = 2
                    avg_px = (avg_px + reentry_p) / 2.0
                    tp_p = avg_px * (1.0 - tp_arr[entry_idx]/100.0)
                    sl_p = avg_px * (1.0 + sl/100.0)
                
                if l[i] <= tp_p:
                    ret = (tp_arr[entry_idx]/100.0 - 2*fee/100.0 - 2*slippage/100.0)
                    trades.append({'res': 1, 'ret': ret, 'units': units})
                    pos = 0; cooldown_cnt = cf['cooldown']
                elif h[i] >= sl_p:
                    ret = (-sl/100.0 - 2*fee/100.0 - 2*slippage/100.0)
                    trades.append({'res': -1, 'ret': ret, 'units': units})
                    pos = 0; cooldown_cnt = cf['cooldown']
    
    # Calculate Compounded Equity Curve based on STRICT RISK %
    equity = 10000.0 # Start with $10,000
    max_equity = 10000.0
    max_dd = 0.0
    
    # Non-compounded strictly (Flat 10000 base)
    equity_flat = 10000.0
    
    for r in trades:
        # The true % return on the account depends on the position size
        # If we risk exactly 1% of account on SL:
        # Sl is 1.9%. So position size is Account * (1% / 1.9%)
        pos_size_fraction = (risk_per_unit_pct / 100.0) / (sl / 100.0)
        
        # Dollar return = Position Size * Trade % Return
        # Multiply by units! (If units=2, the position size was doubled!)
        trade_dollar_return = (equity * pos_size_fraction * r['units']) * r['ret']
        equity += trade_dollar_return
        
        flat_dollar_return = (10000.0 * pos_size_fraction * r['units']) * r['ret']
        equity_flat += flat_dollar_return
        
        if equity > max_equity:
            max_equity = equity
        else:
            dd = (max_equity - equity) / max_equity * 100.0
            if dd > max_dd:
                max_dd = dd
                
    total_ret_compounded = (equity / 10000.0 - 1) * 100
    total_ret_flat = (equity_flat / 10000.0 - 1) * 100
    win_rate = len([x for x in trades if x['res']==1]) / len(trades) * 100 if len(trades)>0 else 0
    return total_ret_compounded, total_ret_flat, max_dd, win_rate

print("\n=== REALISTIC STRESS TEST ===")
print("Parameters: 0.05% Slippage added to EVERY trade, Fixed Risk Sizing applied.\n")

res_2pct_none = simulate_reentry_stress(None, 2.0)
res_2pct_re = simulate_reentry_stress(1.5, 2.0)

print("[1] V23 ASLI (Tanpa Re-Entry)")
print(f"    Skenario: Risiko 2% Modal per transaksi.")
print(f"    Win Rate:      {res_2pct_none[3]:.2f}%")
print(f"    Max Drawdown:  {res_2pct_none[2]:.2f}%")
print(f"    Return FIX:    +{res_2pct_none[1]:.2f}% (Tanpa Compounding)")
print(f"    Return COMPOUND: +{res_2pct_none[0]:.2f}% (Modal digulung tiap trade)\n")

print("[2] V23 DCA (Re-Entry @ -1.5%)")
print(f"    Skenario: Risiko 2% per peluru (Maks 4% jika kena SL 2 peluru).")
print(f"    Win Rate:      {res_2pct_re[3]:.2f}%")
print(f"    Max Drawdown:  {res_2pct_re[2]:.2f}%")
print(f"    Return FIX:    +{res_2pct_re[1]:.2f}% (Tanpa Compounding)")
print(f"    Return COMPOUND: +{res_2pct_re[0]:.2f}% (Modal digulung tiap trade)\n")
