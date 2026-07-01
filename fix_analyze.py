import numpy as np, pandas as pd
import eng

df = pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])

cf = dict(eng.DEF)
res, trades_raw = eng.run(df, cf)
print(trades_raw[0])
