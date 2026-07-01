#!/usr/bin/env python3
"""Adaptasi v20 ke TF 5m. Naive-port (param 15m apa adanya) + rekalibrasi (EMA/TP/SL/cooldown utk 5m).
Data btc_5m_full.csv 716k bar. Banding vs v20-15m (+3327/dd11/wr64/cal303). Validasi full+per-year+OOS."""
import numpy as np, pandas as pd
from eng import rsi,ema,atr,signals,DEF,run as eng_run
from bot_v20_funding import pbsig,TP_BASE,TP_GENTLE,TP_WALL,SL_V20
HERE="/home/dnayaka/Documents/dynamic_rsi/btc-terminal"
d5=pd.read_csv(HERE+"/btc_5m_full.csv")
d5['dt']=pd.to_datetime(d5['open_time'],unit='ms')
d5=d5.dropna().reset_index(drop=True)
year=d5['dt'].dt.year.to_numpy()

def build(ema_len=200, tp_base=2.0, tp_gentle=2.15, tp_wall=0.40, sl=1.9, atr_len=14, rsi_len=14):
    o=d5['open'].to_numpy(float);h=d5['high'].to_numpy(float);l=d5['low'].to_numpy(float);c=d5['close'].to_numpy(float)
    n=len(c)
    R=rsi(c,rsi_len);E=ema(c,ema_len);A=atr(h,l,c,atr_len)
    ap=A/c*100;rng=np.maximum(h-l,1e-9);bodyr=np.abs(c-o)/rng
    aL=pbsig(o,h,l,c,R,E,ap,bodyr,'long');aS=pbsig(o,h,l,c,R,E,ap,bodyr,'short')
    TPa=np.full(n,tp_base);TPa[ap>tp_wall]=tp_gentle;SLa=np.full(n,sl)
    return o,h,l,c,R,E,A,aL,aS,TPa,SLa,n

def runcfg(cfg_over=None, ema_len=200, tp_base=2.0, sl=1.9, cooldown=6, **bk):
    o,h,l,c,R,E,A,aL,aS,TPa,SLa,n=build(ema_len=ema_len,tp_base=tp_base,sl=sl,**bk)
    cf=dict(DEF); cf.update(ema_len=ema_len,cooldown=cooldown)
    if cfg_over: cf.update(cfg_over)
    df5=pd.DataFrame({'open':o,'high':h,'low':l,'close':c,'dt':d5['dt']})
    r,t=eng_run(df5,{**cf,'add_long':aL,'add_short':aS,'tp':TPa,'sl':SLa})
    return r,t,n

def peryear(t):
    yy=year[t['exit_bar'].to_numpy()];g=pd.DataFrame({'y':yy,'net':t['net'].to_numpy()})
    return {int(y):round((np.prod(1+gg['net'])-1)*100,1) for y,gg in g.groupby('y')}
def oostest(t,n):
    cut=int(n*0.70);te=t[t['exit_bar']>=cut]
    if len(te)==0:return 0
    eq=np.cumprod(1+te['net'].to_numpy());pk=np.maximum.accumulate(eq);dd=((pk-eq)/pk).max()*100
    return round((eq[-1]-1)*100/dd,1) if dd>0 else 0

if __name__=='__main__':
    print(f"5m data: {len(d5)} bar, {d5.dt.min()} -> {d5.dt.max()}")
    print("REF v20-15m: ret+3327 dd11.0 wr64.3 n557 cal303 | TEST21.9")
    print()
    print("=== A) NAIVE port (param 15m apa adanya di 5m) ===")
    r,t,n=runcfg(ema_len=200,tp_base=2.0,sl=1.9,cooldown=6)
    print(f'  ret{r["ret"]:+.0f} dd{r["dd"]} wr{r["wr"]} n{r["n"]} cal{r["calmar"]} | TEST{oostest(t,n)} allpos={all(v>0 for v in peryear(t).values())}')
    print()
    print("=== B) EMA di-scale (5m EMA600≈15m EMA200 wall-clock) ===")
    for el in [400,600,800]:
        r,t,n=runcfg(ema_len=el,tp_base=2.0,sl=1.9,cooldown=6)
        print(f'  EMA{el}: ret{r["ret"]:+.0f} dd{r["dd"]} wr{r["wr"]} n{r["n"]} cal{r["calmar"]} | TEST{oostest(t,n)}')
    print()
    print("=== C) rekalibrasi TP/SL (EMA600) ===")
    for tp,sl in [(1.2,1.2),(1.5,1.4),(2.0,1.9),(2.5,2.4),(3.0,2.8)]:
        r,t,n=runcfg(ema_len=600,tp_base=tp,sl=sl,cooldown=6)
        print(f'  TP{tp}/SL{sl}: ret{r["ret"]:+.0f} dd{r["dd"]} wr{r["wr"]} n{r["n"]} cal{r["calmar"]} | TEST{oostest(t,n)}')
    print()
    print("=== D) cooldown scale (5m cd18≈15m cd6 wall-clock) ===")
    for cd in [6,12,18,24]:
        r,t,n=runcfg(ema_len=600,tp_base=2.0,sl=1.9,cooldown=cd)
        print(f'  cd{cd}: ret{r["ret"]:+.0f} dd{r["dd"]} wr{r["wr"]} n{r["n"]} cal{r["calmar"]} | TEST{oostest(t,n)}')
