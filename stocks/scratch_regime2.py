import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import numpy as np, pandas as pd
import pf, seng

data = pf.load_data()
idx = pf.index_df()
ix = idx.copy().sort_values('dt').reset_index(drop=True)
c = ix['close'].to_numpy(float)
def sma(x,n):
    s=pd.Series(x); return s.rolling(n).mean().to_numpy()
ix['sma50']=sma(c,50); ix['sma100']=sma(c,100); ix['sma200']=sma(c,200)
ix['peak252']=pd.Series(c).rolling(252,min_periods=20).max().to_numpy()
ix['ddfrom']=(c/ix['peak252']-1.0)*100

T0 = pf.all_trades(data, pf.CAND)
T0=T0.sort_values('ed').reset_index(drop=True)

# attach index level/regime at entry (prior day)
reg=ix[['dt','close','sma50','sma100','sma200','ddfrom']].copy()
for col in ['close','sma50','sma100','sma200','ddfrom']:
    reg[col]=reg[col].shift(1)
reg['idt']=reg['dt']
M=pd.merge_asof(T0, reg.sort_values('idt'), left_on='ed', right_on='idt', direction='backward')

# 2026 trades
print("=== 2026 trades (by entry date) ===")
m26=M[pd.to_datetime(M['ed']).dt.year==2026]
print("count:", len(m26), " mean net%:", round(m26['net'].mean()*100,3), " wr:", round((m26['net']>0).mean()*100,1))
print(m26[['ed','xd','sym','net','close','sma50','sma200','ddfrom']].to_string())

print("\n=== full-year net mean by exit year (baseline) ===")
print(pf.per_year(T0))

# index level over 2026
print("\n=== JKSE 2026 monthly close ===")
ix26=ix[pd.to_datetime(ix['dt']).dt.year>=2025].copy()
ix26['ym']=pd.to_datetime(ix26['dt']).dt.to_period('M')
print(ix26.groupby('ym').agg(close=('close','last'), dd=('ddfrom','last')).to_string())
