import numpy as np, pandas as pd
import eng, itertools

df = pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])
dt = df['dt'].dt.year
idx_split = df[dt == 2024].index[0]
df_train = df.iloc[:idx_split].copy()
df_test = df.iloc[idx_split:].copy()
df_train.reset_index(drop=True, inplace=True)
df_test.reset_index(drop=True, inplace=True)

def get_squeeze_sig(df_period, cf):
    o = df_period['open'].values
    h = df_period['high'].values
    l = df_period['low'].values
    c = df_period['close'].values
    v = df_period['volume'].values
    hlc3 = (h + l + c) / 3.0
    
    # 1. Rolling VWAP (using e.g., 96 bars = 1 day on 15m)
    vwap_len = cf.get('vwap_len', 200)
    vol_hlc3 = v * hlc3
    vwap = pd.Series(vol_hlc3).rolling(vwap_len).sum() / pd.Series(v).rolling(vwap_len).sum()
    vwap = vwap.values
    
    # 2. RSI
    rsi_len = 14
    up = c - np.roll(c, 1); up[0] = 0
    dn = np.roll(c, 1) - c; dn[0] = 0
    u = np.where(up > 0, up, 0)
    d = np.where(dn > 0, dn, 0)
    urma = eng.rma(u, rsi_len)
    drma = eng.rma(d, rsi_len)
    rs = urma / np.where(drma == 0, 1, drma)
    rsi = np.where(drma == 0, 100, 100 - (100 / (1 + rs)))
    
    # 3. Squeeze
    bb_len = 20
    bb_mult = 2.0
    kc_mult = 1.5
    
    basis = pd.Series(c).rolling(bb_len).mean().values
    dev = pd.Series(c).rolling(bb_len).std(ddof=0).values
    upperBB = basis + bb_mult * dev
    lowerBB = basis - bb_mult * dev
    
    tr1 = h - l
    tr2 = np.abs(h - np.roll(c,1))
    tr3 = np.abs(l - np.roll(c,1))
    tr = np.maximum(tr1, np.maximum(tr2, tr3)); tr[0] = 0
    
    atr = pd.Series(tr).rolling(bb_len).mean().values
    upperKC = basis + kc_mult * atr
    lowerKC = basis - kc_mult * atr
    
    is_squeezed = (lowerBB > lowerKC) & (upperBB < upperKC)
    
    # Fire condition: just released from squeeze
    # We want current bar to NOT be squeezed, but previous bar WAS squeezed
    squeeze_release = (~is_squeezed) & np.roll(is_squeezed, 1)
    squeeze_release[0] = False
    
    # Trend alignment
    trend_up = c > vwap
    trend_dn = c < vwap
    
    long_cond = squeeze_release & trend_up & (rsi > 50)
    short_cond = squeeze_release & trend_dn & (rsi < 50)
    
    return long_cond, short_cond, atr / c * 100.0

cf_base = dict(eng.DEF)
cf_base['sl'] = 2.0
cf_base['tp'] = 3.0

print("Evaluating Squeeze-VWAP strategy on TRAIN (2019-2023)...")
results = []
vwap_opts = [50, 100, 200, 300]
sl_opts = [1.5, 2.0, 2.5]
tp_opts = [2.0, 3.0, 4.0, 5.0]

for vlen, sl, tp in itertools.product(vwap_opts, sl_opts, tp_opts):
    cf = dict(cf_base)
    cf['vwap_len'] = vlen
    l_cond, s_cond, atr_pct = get_squeeze_sig(df_train, cf)
    
    cf['add_long'] = l_cond
    cf['add_short'] = s_cond
    # Mute the original base entry completely
    cf['ob'] = 100
    cf['os'] = 0
    cf['sl'] = sl
    cf['tp'] = tp
    
    res, _ = eng.run(df_train, cf)
    if res['dd'] > 0:
        results.append({
            'vwap_len': vlen, 'sl': sl, 'tp': tp,
            'ret': res['ret'], 'dd': res['dd'], 'wr': res['wr'], 'calmar': res['calmar'], 'n': res['n']
        })

r_df = pd.DataFrame(results)
r_df.sort_values('ret', ascending=False, inplace=True)
print("\n--- TOP SQUEEZE CONFIGS IN TRAIN ---")
print(r_df.head(10))

# Wait, the number of trades might be too low.
print("\nBest by Calmar:")
r_df.sort_values('calmar', ascending=False, inplace=True)
print(r_df.head(5))

