#!/usr/bin/env python3
"""EXP2: DCA sekali di X% adverse pada v20. Fork eng.run dgn averaging-down.
Model: entry 1 unit; kalau harga gerak X% lawan SEBELUM TP/SL -> add 1 unit (avg down),
TP/SL dihitung ulang % dari avg. Sweep X. Banding ret/dd/wr/calmar vs baseline.
NOTE: add = 2x exposure di trade rugi -> DD bisa naik; Calmar yg jadi hakim (bukan ret mentah)."""
import numpy as np, pandas as pd
from eng import rsi, ema, atr, signals, indicators, DEF, run as eng_run
from bot_v20_funding import pbsig, TP_BASE, TP_GENTLE, TP_WALL, SL_V20

HERE="/home/dnayaka/Documents/dynamic_rsi/btc-terminal"
df=pd.read_csv(HERE+"/btc_15m_full.csv",parse_dates=['dt'])
o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float);c=df['close'].to_numpy(float)
n=len(c)
R=rsi(c,DEF['rsi_len']);E=ema(c,DEF['ema_len']);A=atr(h,l,c,DEF['atr_len'])
ap=A/c*100.0; rng=h-l; body=np.where(rng>0,np.abs(c-o)/np.where(rng>0,rng,1),0.0)
aL=pbsig(o,h,l,c,R,E,ap,body,'long'); aS=pbsig(o,h,l,c,R,E,ap,body,'short')
TPa=np.full(n,TP_BASE); TPa[ap>TP_WALL]=TP_GENTLE
SLa=np.full(n,SL_V20)
yb=df['dt'].dt.year.to_numpy()

def run_dca(dca_pct=None):
    """dca_pct=None -> baseline (faithful eng). else add 1 unit di X% adverse."""
    cf=dict(DEF)
    long_sig,short_sig,atr_pct,_=signals(df,{**cf,'add_long':aL,'add_short':aS},(o,h,l,c,R,E,A))
    fee=cf['fee']; cd=cf['cooldown']; start=max(cf['warmup'],cf['ema_len']+2)
    use_tr=cf['use_trail']; tmult=cf['trail_mult']; tmin=cf['trail_min']; tmax=cf['trail_max']; tact=cf['trail_act']
    pos=0; entry=0.0; entry_bar=0; tp=sl=0.0; tpct=spct=0.0; avg=0.0; units=1; added=False; dca_px=0.0
    last_exit_dir=0; last_exit_bar=-10**9; pending=0; trades=[]; hi=lo=0.0; trail=np.nan; gap=0.0
    for i in range(start,n):
        if pending!=0 and pos==0:
            entry=o[i]; entry_bar=i; pos=pending; avg=entry; units=1; added=False
            tpct=TPa[i-1]; spct=SLa[i-1]
            if pos>0: tp=avg*(1+tpct/100); sl=avg*(1-spct/100)
            else:     tp=avg*(1-tpct/100); sl=avg*(1+spct/100)
            gap=max(tmin*avg/100,min(tmax*avg/100,a_i(i)*tmult)); hi=h[i]; lo=l[i]; trail=np.nan; pending=0
        if pos!=0:
            # --- DCA add (sebelum cek exit) ---
            if dca_pct and not added:
                if pos>0:
                    addlvl=entry*(1-dca_pct/100)
                    if l[i]<=addlvl and addlvl>sl:   # cuma kalau add-level di atas SL (kalau ga, SL duluan)
                        dca_px=addlvl; units=2; added=True; avg=(entry+dca_px)/2
                        tp=avg*(1+tpct/100); sl=avg*(1-spct/100); gap=max(tmin*avg/100,min(tmax*avg/100,a_i(i)*tmult))
                else:
                    addlvl=entry*(1+dca_pct/100)
                    if h[i]>=addlvl and addlvl<sl:
                        dca_px=addlvl; units=2; added=True; avg=(entry+dca_px)/2
                        tp=avg*(1-tpct/100); sl=avg*(1+spct/100); gap=max(tmin*avg/100,min(tmax*avg/100,a_i(i)*tmult))
            if pos>0:
                stop=sl if np.isnan(trail) else max(sl,trail)
                ex=None;px=0.0
                if l[i]<=stop: px=min(o[i],stop) if o[i]<stop else stop; ex='SL'
                elif h[i]>=tp: px=max(o[i],tp) if o[i]>tp else tp; ex='TP'
                if ex:
                    net=(px/entry-1)+((px/dca_px-1) if added else 0.0)-2*fee*units
                    trades.append((entry_bar,i,pos,net,units)); pos=0;last_exit_dir=1;last_exit_bar=i;added=False;units=1
                else:
                    hi=max(hi,h[i])
                    if use_tr and (hi-avg)>=tact*avg/100: nt=hi-gap; trail=nt if np.isnan(trail) else max(trail,nt)
            else:
                stop=sl if np.isnan(trail) else min(sl,trail)
                ex=None;px=0.0
                if h[i]>=stop: px=max(o[i],stop) if o[i]>stop else stop; ex='SL'
                elif l[i]<=tp: px=min(o[i],tp) if o[i]<tp else tp; ex='TP'
                if ex:
                    net=(entry/px-1)+((dca_px/px-1) if added else 0.0)-2*fee*units
                    trades.append((entry_bar,i,pos,net,units)); pos=0;last_exit_dir=-1;last_exit_bar=i;added=False;units=1
                else:
                    lo=min(lo,l[i])
                    if use_tr and (avg-lo)>=tact*avg/100: nt=lo+gap; trail=nt if np.isnan(trail) else min(trail,nt)
        if pos==0 and pending==0:
            bse=i-last_exit_bar
            cdL=not(last_exit_dir==1 and bse<cd); cdS=not(last_exit_dir==-1 and bse<cd)
            if long_sig[i] and cdL: pending=1
            elif short_sig[i] and cdS: pending=-1
    t=pd.DataFrame(trades,columns=['eb','xb','dir','net','units'])
    if len(t)==0: return dict(n=0),t
    eq=np.cumprod(1+cf['lev']*t['net'].to_numpy())
    peak=np.maximum.accumulate(eq); dd=((peak-eq)/peak).max()*100
    ret=(eq[-1]-1)*100; wr=(t['net']>0).mean()*100
    gp=t.loc[t['net']>0,'net'].sum(); gl=-t.loc[t['net']<0,'net'].sum(); pf=gp/gl if gl>0 else np.inf
    nadd=int(t['units'].eq(2).sum())
    return dict(n=len(t),ret=round(ret,1),dd=round(dd,2),wr=round(wr,2),
                calmar=round(ret/dd,1) if dd>0 else 0,pf=round(pf,2),nadd=nadd),t
_A=A
def a_i(i): return _A[i]

def peryear(t,lev=1.0):
    if len(t)==0: return {}
    t=t.copy(); t['y']=[yb[int(x)] for x in t['xb']]; out={}
    for y,g in t.groupby('y'):
        eq=np.cumprod(1+lev*g['net'].to_numpy()); out[int(y)]=round((eq[-1]-1)*100,1)
    return out

print("=== BASELINE (fork, harus ~+3327/dd11/wr64) ===")
r0,t0=run_dca(None); print(r0)
print("\n=== DCA sweep (add 1 unit di X% adverse) ===")
print(f"{'X%':>5} {'ret':>8} {'dd':>7} {'wr':>6} {'calmar':>7} {'pf':>5} {'nadd':>5}")
for X in [0.4,0.5,0.6,0.7,0.8,0.9,1.0,1.1,1.2,1.3,1.5,1.7]:
    r,t=run_dca(X)
    print(f"{X:>5} {r['ret']:>+8.0f} {r['dd']:>7} {r['wr']:>6} {r['calmar']:>7} {r['pf']:>5} {r['nadd']:>5}")

print("\n=== VALIDASI per-year (all-positive?) ===")
for X in [None,0.4,0.9,1.0,1.5]:
    r,t=run_dca(X); py=peryear(t)
    allpos=all(v>0 for v in py.values())
    print(f"X={str(X):>5} calmar {r['calmar']:>6} allpos {allpos}  {py}")

print("\n=== OOS: train 70% / test 30% (X terbaik konsisten?) ===")
cut=int(n*0.70)
def run_dca_slice(dca_pct,lo,hi):
    r,t=run_dca(dca_pct)
    t=t[(t['xb']>=lo)&(t['xb']<hi)]
    if len(t)==0: return dict(n=0,ret=0,dd=0,calmar=0)
    eq=np.cumprod(1+t['net'].to_numpy()); peak=np.maximum.accumulate(eq)
    dd=((peak-eq)/peak).max()*100; ret=(eq[-1]-1)*100
    return dict(n=len(t),ret=round(ret,0),dd=round(dd,2),wr=round((t['net']>0).mean()*100,1),calmar=round(ret/dd,1) if dd>0 else 0)
print(f"{'X':>5} | {'TRAIN ret/dd/cal':>22} | {'TEST ret/dd/cal':>22}")
for X in [None,0.4,0.6,0.8,0.9,1.0,1.1,1.5]:
    tr=run_dca_slice(X,0,cut); te=run_dca_slice(X,cut,n)
    print(f"{str(X):>5} | {tr['ret']:>+8.0f} {tr['dd']:>5} {tr['calmar']:>6} | {te['ret']:>+8.0f} {te['dd']:>5} {te['calmar']:>6}")
