#!/usr/bin/env python3
"""v23 riset: restrukturisasi TP (partial/scale-out + BE + TP2) & give-back trail (exit cepat pas balik).
Fork faithful eng.run. Semua mode fallback ke baseline v20 kalau knob mati -> harus repro +3327/dd11/wr64.
Validasi: full-period + per-year all-positive + OOS train70/test30. Calmar hakim (bukan ret mentah)."""
import numpy as np, pandas as pd
from eng import rsi, ema, atr, signals, indicators, DEF
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

def run_v23(tp1=None, f1=0.0, tp2=None, be_after=False, gb_act=None, gb_frac=None, sl_over=None):
    """Knobs:
      tp1/f1     : partial close fraksi f1 di level tp1% (scale-out). tp2 = target sisa.
      be_after   : stop sisa -> entry setelah tp1 kena.
      gb_act/gb_frac : give-back trail. Aktif saat gain>=gb_act%. Exit sisa saat harga retrace gb_frac dari PUNCAK-gain.
      sl_over    : override SL% (statis). None -> SLa (1.9 regime).
    Semua None/0 -> baseline v20 (trail chandelier bawaan)."""
    cf=dict(DEF)
    long_sig,short_sig,atr_pct,_=signals(df,{**cf,'add_long':aL,'add_short':aS},(o,h,l,c,R,E,A))
    fee=cf['fee']; cd=cf['cooldown']; start=max(cf['warmup'],cf['ema_len']+2)
    use_tr=cf['use_trail']; tmult=cf['trail_mult']; tmin=cf['trail_min']; tmax=cf['trail_max']; tact=cf['trail_act']
    pos=0; entry=0.0; entry_bar=0; tp=sl=0.0; tpct=spct=0.0
    last_exit_dir=0; last_exit_bar=-10**9; pending=0; trades=[]
    hi=lo=0.0; trail=np.nan; gap=0.0
    rem=1.0; locked=0.0; t1done=False; peak=0.0   # peak = puncak gain% (utk gb trail)
    for i in range(start,n):
        if pending!=0 and pos==0:
            entry=o[i]; entry_bar=i; pos=pending
            tpct=TPa[i-1]; spct=(sl_over if sl_over is not None else SLa[i-1])
            if pos>0: tp=entry*(1+tpct/100); sl=entry*(1-spct/100)
            else:     tp=entry*(1-tpct/100); sl=entry*(1+spct/100)
            gap=max(tmin*entry/100,min(tmax*entry/100,A[i]*tmult)); hi=h[i]; lo=l[i]; trail=np.nan; pending=0
            rem=1.0; locked=0.0; t1done=False; peak=0.0
        if pos!=0:
            if pos>0:
                # adverse-first: SL/trail dulu (sisa penuh)
                stop=sl if np.isnan(trail) else max(sl,trail)
                ex=None; px=0.0
                if l[i]<=stop: px=min(o[i],stop) if o[i]<stop else stop; ex='SL'
                elif h[i]>=tp: px=max(o[i],tp) if o[i]>tp else tp; ex='TP'
                # partial TP1 (kalau belum exit penuh & belum t1done & tp1 set)
                if ex is None and tp1 and not t1done and h[i]>=entry*(1+tp1/100):
                    p1=entry*(1+tp1/100); locked+=f1*(p1/entry-1); rem-=f1; t1done=True
                    if be_after: sl=max(sl,entry)
                    if tp2: tp=entry*(1+tp2/100)
                # give-back trail (sisa): update peak, cek retrace
                if ex is None and gb_act is not None:
                    peak=max(peak,(h[i]-entry)/entry*100)
                    if peak>=gb_act:
                        gbstop=entry*(1+(peak*(1-gb_frac))/100)
                        if l[i]<=gbstop: px=min(o[i],gbstop) if o[i]<gbstop else gbstop; ex='GB'
                if ex:
                    net=locked+rem*((px/entry-1)) -2*fee
                    trades.append((entry_bar,i,pos,net)); pos=0;last_exit_dir=1;last_exit_bar=i
                else:
                    hi=max(hi,h[i])
                    if use_tr and (hi-entry)>=tact*entry/100: nt=hi-gap; trail=nt if np.isnan(trail) else max(trail,nt)
            else:
                stop=sl if np.isnan(trail) else min(sl,trail)
                ex=None; px=0.0
                if h[i]>=stop: px=max(o[i],stop) if o[i]>stop else stop; ex='SL'
                elif l[i]<=tp: px=min(o[i],tp) if o[i]<tp else tp; ex='TP'
                if ex is None and tp1 and not t1done and l[i]<=entry*(1-tp1/100):
                    p1=entry*(1-tp1/100); locked+=f1*(entry/p1-1); rem-=f1; t1done=True
                    if be_after: sl=min(sl,entry)
                    if tp2: tp=entry*(1-tp2/100)
                if ex is None and gb_act is not None:
                    peak=max(peak,(entry-l[i])/entry*100)
                    if peak>=gb_act:
                        gbstop=entry*(1-(peak*(1-gb_frac))/100)
                        if h[i]>=gbstop: px=max(o[i],gbstop) if o[i]>gbstop else gbstop; ex='GB'
                if ex:
                    net=locked+rem*((entry/px-1)) -2*fee
                    trades.append((entry_bar,i,pos,net)); pos=0;last_exit_dir=-1;last_exit_bar=i
                else:
                    lo=min(lo,l[i])
                    if use_tr and (entry-lo)>=tact*entry/100: nt=lo+gap; trail=nt if np.isnan(trail) else min(trail,nt)
        if pos==0 and pending==0:
            bse=i-last_exit_bar
            cdL=not(last_exit_dir==1 and bse<cd); cdS=not(last_exit_dir==-1 and bse<cd)
            if long_sig[i] and cdL: pending=1
            elif short_sig[i] and cdS: pending=-1
    t=pd.DataFrame(trades,columns=['eb','xb','dir','net'])
    return metrics(t),t

def metrics(t,lev=1.0):
    if len(t)==0: return dict(n=0)
    eq=np.cumprod(1+lev*t['net'].to_numpy()); peak=np.maximum.accumulate(eq)
    dd=((peak-eq)/peak).max()*100; ret=(eq[-1]-1)*100; wr=(t['net']>0).mean()*100
    gp=t.loc[t['net']>0,'net'].sum(); gl=-t.loc[t['net']<0,'net'].sum(); pf=gp/gl if gl>0 else np.inf
    return dict(n=len(t),ret=round(ret,1),dd=round(dd,2),wr=round(wr,2),
                calmar=round(ret/dd,1) if dd>0 else 0,pf=round(pf,2))

def peryear(t):
    if len(t)==0: return {}
    t=t.copy(); t['y']=[yb[int(x)] for x in t['xb']]; out={}
    for y,g in t.groupby('y'):
        eq=np.cumprod(1+g['net'].to_numpy()); out[int(y)]=round((eq[-1]-1)*100,1)
    return out

def oos(fn_kwargs):
    cut=int(n*0.70)
    _,t=run_v23(**fn_kwargs)
    tr=t[t['xb']<cut]; te=t[t['xb']>=cut]
    return metrics(tr),metrics(te)

if __name__=='__main__':
    print("=== BASELINE (semua knob off) ===")
    r0,t0=run_v23(); print(r0); print("per-year:",peryear(t0))
    base_cal=r0['calmar']

    print("\n=== A) PARTIAL TP1 (scale-out) + BE, sisa ke TP2=2.0/2.5 ===")
    print(f"{'tp1':>4}{'f1':>5}{'tp2':>5}{'be':>4} | {'ret':>8}{'dd':>7}{'wr':>7}{'cal':>7}{'pf':>6}")
    for tp1 in [0.8,1.0,1.2,1.5]:
        for f1 in [0.25,0.5,0.75]:
            for tp2 in [2.0,2.5,3.0]:
                for be in [False,True]:
                    r,_=run_v23(tp1=tp1,f1=f1,tp2=tp2,be_after=be)
                    flag='' if r['calmar']<=base_cal else '  <==BEAT'
                    if r['calmar']>=base_cal*0.9:
                        print(f"{tp1:>4}{f1:>5}{tp2:>5}{str(be):>5} | {r['ret']:>+8.0f}{r['dd']:>7}{r['wr']:>7}{r['calmar']:>7}{r['pf']:>6}{flag}")

    print("\n=== B) GIVE-BACK TRAIL (exit cepat pas balik, retrace gb_frac dari puncak) ===")
    print(f"{'act':>5}{'frac':>6} | {'ret':>8}{'dd':>7}{'wr':>7}{'cal':>7}{'pf':>6}")
    for act in [0.6,0.8,1.0,1.2,1.5]:
        for fr in [0.3,0.4,0.5,0.6]:
            r,_=run_v23(gb_act=act,gb_frac=fr)
            flag='  <==BEAT' if r['calmar']>base_cal else ''
            print(f"{act:>5}{fr:>6} | {r['ret']:>+8.0f}{r['dd']:>7}{r['wr']:>7}{r['calmar']:>7}{r['pf']:>6}{flag}")
