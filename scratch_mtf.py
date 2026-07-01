#!/usr/bin/env python3
"""v23 MTF test: entry 15m v20; saat PROFIT running & RSI LTF (5m + fast-proxy 3m/1m via RSI7) OVERBOUGHT
-> TP dulu (exit di 5m close). Pas RSI LTF MENGECIL (cool) & tren 15m msh dukung -> RE-ENTRY.
Eksekusi grid 5m (bukan intrabar-15m) -> hindari look-ahead. Baseline-5m-grid = pembanding apples-to-apples."""
import numpy as np, pandas as pd
from eng import rsi, ema, atr, signals, DEF
from bot_v20_funding import pbsig, TP_BASE, TP_GENTLE, TP_WALL, SL_V20

HERE="/home/dnayaka/Documents/dynamic_rsi/btc-terminal"
d15=pd.read_csv(HERE+"/btc_15m_full.csv",parse_dates=['dt'])
d5=pd.read_csv(HERE+"/btc_5m_full.csv")
# 15m arrays + v20 signals
o=d15['open'].to_numpy(float);h=d15['high'].to_numpy(float);l=d15['low'].to_numpy(float);c=d15['close'].to_numpy(float)
n15=len(c); ot15=d15['open_time'].to_numpy(np.int64)
R15=rsi(c,DEF['rsi_len']);E15=ema(c,DEF['ema_len']);A15=atr(h,l,c,DEF['atr_len'])
ap15=A15/c*100.0; rng=h-l; body=np.where(rng>0,np.abs(c-o)/np.where(rng>0,rng,1),0.0)
aL=pbsig(o,h,l,c,R15,E15,ap15,body,'long'); aS=pbsig(o,h,l,c,R15,E15,ap15,body,'short')
LS,SS,_,_=signals(d15,{**DEF,'add_long':aL,'add_short':aS},(o,h,l,c,R15,E15,A15))
TPa=np.full(n15,TP_BASE); TPa[ap15>TP_WALL]=TP_GENTLE; SLa=np.full(n15,SL_V20)
# 5m arrays
o5=d5['open'].to_numpy(float);h5=d5['high'].to_numpy(float);l5=d5['low'].to_numpy(float);c5=d5['close'].to_numpy(float)
ot5=d5['open_time'].to_numpy(np.int64); n5=len(c5)
R5=rsi(c5,14); R5f=rsi(c5,7)   # 5m std + fast (proxy 3m/1m)
# parent 15m index tiap 5m bar
par=np.searchsorted(ot15,ot5,side='right')-1
yb5=pd.to_datetime(d5['open_time'],unit='ms').dt.year.to_numpy()
BAR15=15*60*1000

def metrics(t,lev=1.0):
    if len(t)==0: return dict(n=0)
    eq=np.cumprod(1+lev*t['net'].to_numpy()); pk=np.maximum.accumulate(eq)
    dd=((pk-eq)/pk).max()*100; ret=(eq[-1]-1)*100; wr=(t['net']>0).mean()*100
    gp=t.loc[t['net']>0,'net'].sum(); gl=-t.loc[t['net']<0,'net'].sum(); pf=gp/gl if gl>0 else np.inf
    return dict(n=len(t),ret=round(ret,1),dd=round(dd,2),wr=round(wr,2),calmar=round(ret/dd,1) if dd>0 else 0,pf=round(pf,2))
def peryear(t):
    if len(t)==0: return {}
    t=t.copy(); t['y']=[int(yb5[int(x)]) for x in t['xb']]; out={}
    for y,g in t.groupby('y'):
        eq=np.cumprod(1+g['net'].to_numpy()); out[int(y)]=round((eq[-1]-1)*100,1)
    return out

def run_mtf(mtf=False, ob5=72, cool=50, minp=0.3, rewin=24, maxre=3, usefast=False, sl=None):
    """mtf=False -> baseline 5m-grid v20 (harus mendekati +3327). mtf=True -> aktif exit/re-entry LTF."""
    fee=DEF['fee']; cd=DEF['cooldown']; tmult=DEF['trail_mult']; tmin=DEF['trail_min']; tmax=DEF['trail_max']; tact=DEF['trail_act']
    RR = R5f if usefast else R5
    pos=0; entry=0.0; eb=0; tp=slp=0.0; led=0; leb15=-10**9; trades=[]
    trail=np.nan; gap=0.0; hi=lo=0.0
    ref=0.0; rdir=0; rexp=-1; rmin=-1; reidx=0
    start5=int(np.searchsorted(ot5, ot15[max(DEF['warmup'],DEF['ema_len']+2)]))
    prev_par=par[start5]
    for i in range(start5,n5):
        p=par[i]
        if p<1: continue
        # ---- manage posisi (grid 5m) ----
        if pos!=0:
            spct=slp
            if pos>0:
                stop=slp if np.isnan(trail) else max(slp,trail); ex=None; px=0.0
                if l5[i]<=stop: px=min(o5[i],stop) if o5[i]<stop else stop; ex='SL'
                elif h5[i]>=tp: px=max(o5[i],tp) if o5[i]>tp else tp; ex='TP'
                # MTF exit: profit & LTF overbought -> ambil profit
                if ex is None and mtf and (c5[i]/entry-1)*100>=minp and RR[i]>=ob5:
                    px=c5[i]; ex='MTF'
                if ex:
                    net=(px/entry-1)-2*fee; trades.append((eb,i,pos,net,ex)); pos=0; led=1; leb15=p
                    if mtf and ex=='MTF' and reidx<maxre and c[p]>E15[p]:
                        ref=c5[i]; rdir=1; rexp=i+rewin; rmin=i+1
                    else: rdir=0; reidx=0
                else:
                    hi=max(hi,h5[i])
                    if hi-entry>=tact*entry/100: nt=hi-gap; trail=nt if np.isnan(trail) else max(trail,nt)
            else:
                stop=slp if np.isnan(trail) else min(slp,trail); ex=None; px=0.0
                if h5[i]>=stop: px=max(o5[i],stop) if o5[i]>stop else stop; ex='SL'
                elif l5[i]<=tp: px=min(o5[i],tp) if o5[i]<tp else tp; ex='TP'
                if ex is None and mtf and (entry/c5[i]-1)*100>=minp and RR[i]<=(100-ob5):
                    px=c5[i]; ex='MTF'
                if ex:
                    net=(entry/px-1)-2*fee; trades.append((eb,i,pos,net,ex)); pos=0; led=-1; leb15=p
                    if mtf and ex=='MTF' and reidx<maxre and c[p]<E15[p]:
                        ref=c5[i]; rdir=-1; rexp=i+rewin; rmin=i+1
                    else: rdir=0; reidx=0
                else:
                    lo=min(lo,l5[i])
                    if entry-lo>=tact*entry/100: nt=lo+gap; trail=nt if np.isnan(trail) else min(trail,nt)
        # ---- RE-ENTRY: armed & LTF cool & tren 15m ok ----
        if pos==0 and rdir!=0:
            if i>rexp: rdir=0; reidx=0
            elif rdir>0 and i>=rmin and RR[i]<=cool and c[p]>E15[p]:
                entry=c5[i]; eb=i; pos=1; reidx+=1
                tp=entry*(1+TPa[p]/100); slp=(entry*(1-(sl or SLa[p])/100)); gap=max(tmin*entry/100,min(tmax*entry/100,A15[p]*tmult)); trail=np.nan; hi=h5[i]; lo=l5[i]; rdir=0
            elif rdir<0 and i>=rmin and RR[i]>=(100-cool) and c[p]<E15[p]:
                entry=c5[i]; eb=i; pos=-1; reidx+=1
                tp=entry*(1-TPa[p]/100); slp=(entry*(1+(sl or SLa[p])/100)); gap=max(tmin*entry/100,min(tmax*entry/100,A15[p]*tmult)); trail=np.nan; hi=h5[i]; lo=l5[i]; rdir=0
        # ---- entry baru dari sinyal 15m (di batas bar 15m) ----
        if p!=prev_par and pos==0 and rdir==0:
            sp=p-1  # 15m bar yg BARU tutup
            bse=sp-leb15
            if LS[sp] and not(led==1 and bse<cd):
                entry=o5[i]; eb=i; pos=1; reidx=0
                tp=entry*(1+TPa[sp]/100); slp=entry*(1-(sl or SLa[sp])/100); gap=max(tmin*entry/100,min(tmax*entry/100,A15[sp]*tmult)); trail=np.nan; hi=h5[i]; lo=l5[i]
            elif SS[sp] and not(led==-1 and bse<cd):
                entry=o5[i]; eb=i; pos=-1; reidx=0
                tp=entry*(1-TPa[sp]/100); slp=entry*(1+(sl or SLa[sp])/100); gap=max(tmin*entry/100,min(tmax*entry/100,A15[sp]*tmult)); trail=np.nan; hi=h5[i]; lo=l5[i]
        prev_par=p
    t=pd.DataFrame(trades,columns=['eb','xb','dir','net','ex'])
    return metrics(t),t

if __name__=='__main__':
    print("5m bars:",n5," span:",pd.to_datetime(ot5[0],unit='ms'),"->",pd.to_datetime(ot5[-1],unit='ms'))
    rb,tb=run_mtf(mtf=False)
    print("BASELINE 5m-grid v20:",rb," (ref 15m-eng +3327/dd11/wr64/n557)")
    print("per-year:",peryear(tb))
    print("\n=== MTF exit+re-entry sweep (5m std RSI) ===")
    print(f"{'ob5':>4}{'cool':>5}{'minp':>5}{'maxre':>6} | {'ret':>8}{'dd':>7}{'wr':>7}{'cal':>7}{'n':>6} allpos")
    for ob5 in [70,72,75,80]:
        for cool in [45,50,55]:
            r,t=run_mtf(mtf=True,ob5=ob5,cool=cool,minp=0.3,maxre=3)
            py=peryear(t); apos=all(v>0 for v in py.values())
            print(f"{ob5:>4}{cool:>5}{0.3:>5}{3:>6} | {r['ret']:>+8.0f}{r['dd']:>7}{r['wr']:>7}{r['calmar']:>7}{r['n']:>6} {apos}")
