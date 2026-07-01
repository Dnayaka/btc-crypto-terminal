#!/usr/bin/env python3
"""Riset v20: (1) no-trade FOMC-Wed, (2) DCA sekali di X% adverse. Banding vs baseline.
Pakai eng.py + pbsig dari bot_v20_funding. Validasi: full-period + per-year + OOS split."""
import numpy as np, pandas as pd, datetime as dt
from eng import rsi, ema, atr, signals, indicators, DEF, run as eng_run
from bot_v20_funding import pbsig, TP_BASE, TP_GENTLE, TP_WALL, SL_V20

HERE="/home/dnayaka/Documents/dynamic_rsi/btc-terminal"
df=pd.read_csv(HERE+"/btc_15m_full.csv",parse_dates=['dt'])
o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float);c=df['close'].to_numpy(float)
n=len(c)
R=rsi(c,DEF['rsi_len']);E=ema(c,DEF['ema_len']);A=atr(h,l,c,DEF['atr_len'])
ap=A/c*100.0; rng=h-l; body=np.where(rng>0,np.abs(c-o)/np.where(rng>0,rng,1),0.0)
aL=pbsig(o,h,l,c,R,E,ap,body,'long'); aS=pbsig(o,h,l,c,R,E,ap,body,'short')
tp_arr=np.full(n,TP_BASE); tp_arr[ap>TP_WALL]=TP_GENTLE
sl_arr=np.full(n,SL_V20)
dates=df['dt'].dt.tz_convert('UTC') if df['dt'].dt.tz is not None else df['dt']
ymd=df['dt'].dt.strftime('%Y-%m-%d').to_numpy()
dow=df['dt'].dt.dayofweek.to_numpy()  # 0=Mon..6=Sun
years=df['dt'].dt.year.to_numpy()

# ---- FOMC announcement dates 2019-2026 (hari pengumuman, kebanyakan Rabu) ----
FOMC=set("""
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-03-03 2020-03-15 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17
""".split())

def base_cfg():
    return {'add_long':aL.copy(),'add_short':aS.copy(),'tp':tp_arr,'sl':sl_arr}

def metrics(res,t,lev=1.0):
    if len(t)==0: return res
    return res

def peryear(t,lev=1.0):
    out={}
    if len(t)==0: return out
    yb=df['dt'].dt.year.to_numpy()
    t=t.copy(); t['y']=[yb[int(x)] for x in t['exit_bar']]
    for y,g in t.groupby('y'):
        eq=np.cumprod(1+lev*g['net'].to_numpy()); out[int(y)]=round((eq[-1]-1)*100,1)
    return out

def run_block(block):
    """block = bool array, True = jangan entry bar itu."""
    cfg=base_cfg()
    cfg['add_long']=aL & ~block; cfg['add_short']=aS & ~block
    cfg['extra_long']=~block; cfg['extra_short']=~block
    return eng_run(df,cfg)

# ===== BASELINE =====
res0,t0=eng_run(df,base_cfg())
print("=== BASELINE v20 ===")
print(f"ret {res0['ret']:+.0f}%  dd {res0['dd']}  wr {res0['wr']}  n {res0['n']}  calmar {res0['calmar']}  pf {res0['pf']}  nL/nS {res0['nl']}/{res0['ns']}")
print("per-year:",peryear(t0))

# ===== EXP1: no-trade FOMC Wed =====
print("\n=== EXP1: no-trade FOMC-day ===")
isfomc=np.array([d in FOMC for d in ymd])
print(f"bar FOMC-day: {isfomc.sum()} ({isfomc.sum()/n*100:.1f}%)")
res1,t1=run_block(isfomc)
print(f"FOMC-day block : ret {res1['ret']:+.0f}%  dd {res1['dd']}  wr {res1['wr']}  n {res1['n']}  calmar {res1['calmar']}")
print("per-year:",peryear(t1))
# variant: block FOMC day + day after (volatilitas nyangkut)
isfomc2=isfomc.copy()
for i in range(n-1):
    if isfomc[i]: isfomc2[i+1]=True
res1b,t1b=run_block(isfomc2)
print(f"FOMC +1day block: ret {res1b['ret']:+.0f}%  dd {res1b['dd']}  wr {res1b['wr']}  n {res1b['n']}  calmar {res1b['calmar']}")
# variant: block ALL Wednesdays (proxy kasar)
iswed=(dow==2)
res1c,t1c=run_block(iswed)
print(f"ALL-Wed block  : ret {res1c['ret']:+.0f}%  dd {res1c['dd']}  wr {res1c['wr']}  n {res1c['n']}  calmar {res1c['calmar']}")
