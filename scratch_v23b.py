#!/usr/bin/env python3
"""v23b: quick-TP kecil (0.5%) + RE-ENTRY pas balik arah + sizing STATIC vs DYNAMIC.
Ide user: profit 0.5% -> TP cepat; kalau harga balik ke entry -> re-enter (scalp ulang tren yg sama).
Sizing: static (1 unit) vs dynamic (vol-normalized / decay per re-entry).
Fork faithful v20 signals+cooldown. Validasi full + per-year + OOS."""
import numpy as np, pandas as pd
from eng import signals, DEF
from bot_v20_funding import pbsig, TP_BASE, TP_GENTLE, TP_WALL, SL_V20

HERE="/home/dnayaka/Documents/dynamic_rsi/btc-terminal"
df=pd.read_csv(HERE+"/btc_15m_full.csv",parse_dates=['dt'])
o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float);c=df['close'].to_numpy(float)
n=len(c)
from eng import rsi,ema,atr
R=rsi(c,DEF['rsi_len']);E=ema(c,DEF['ema_len']);A=atr(h,l,c,DEF['atr_len'])
ap=A/c*100.0; rng=h-l; body=np.where(rng>0,np.abs(c-o)/np.where(rng>0,rng,1),0.0)
aL=pbsig(o,h,l,c,R,E,ap,body,'long'); aS=pbsig(o,h,l,c,R,E,ap,body,'short')
yb=df['dt'].dt.year.to_numpy()
apmed=np.nanmedian(ap)   # utk vol-normalize

def size_of(mode, i, reidx):
    """reidx = 0 entry awal, 1.. = re-entry ke-n."""
    if mode=='static': return 1.0
    if mode=='volnorm': return float(np.clip(apmed/ap[i], 0.4, 1.6))   # vol tinggi -> size kecil
    if mode=='decay':   return 0.5**reidx                              # anti-martingale: re-entry mengecil
    if mode=='voldecay':return float(np.clip(apmed/ap[i],0.4,1.6))*(0.6**reidx)
    return 1.0

def run_qtp(tpq=0.5, sl=1.9, reentry=False, rewin=12, maxre=2, sizing='static'):
    cf=dict(DEF)
    long_sig,short_sig,_,_=signals(df,{**cf,'add_long':aL,'add_short':aS},(o,h,l,c,R,E,A))
    fee=cf['fee']; cd=cf['cooldown']; start=max(cf['warmup'],cf['ema_len']+2)
    pos=0; entry=0.0; eb=0; tp=slp=0.0; led=0; leb=-10**9; pend=0; trades=[]
    ref=0.0; rearm_dir=0; rearm_exp=-1; rearm_min=-1; reidx=0; cursize=1.0
    for i in range(start,n):
        # fill pending (signal baru ATAU re-entry)
        if pend!=0 and pos==0:
            entry=o[i]; eb=i; pos=pend
            if pos>0: tp=entry*(1+tpq/100); slp=entry*(1-sl/100)
            else:     tp=entry*(1-tpq/100); slp=entry*(1+sl/100)
            pend=0
        if pos!=0:
            if pos>0:
                ex=None; px=0.0
                if l[i]<=slp: px=min(o[i],slp) if o[i]<slp else slp; ex='SL'
                elif h[i]>=tp: px=max(o[i],tp) if o[i]>tp else tp; ex='TP'
                if ex:
                    net=cursize*((px/entry-1))-2*fee*cursize
                    trades.append((eb,i,pos,net,cursize,ex)); led=1; leb=i; won=(ex=='TP')
                    if reentry and won and reidx<maxre:   # menang & masih boleh re-arm
                        ref=entry; rearm_dir=1; rearm_exp=i+rewin; rearm_min=i+1
                    else: rearm_dir=0; reidx=0
                    pos=0
            else:
                ex=None; px=0.0
                if h[i]>=slp: px=max(o[i],slp) if o[i]>slp else slp; ex='SL'
                elif l[i]<=tp: px=min(o[i],tp) if o[i]<tp else tp; ex='TP'
                if ex:
                    net=cursize*((entry/px-1))-2*fee*cursize
                    trades.append((eb,i,pos,net,cursize,ex)); led=-1; leb=i; won=(ex=='TP')
                    if reentry and won and reidx<maxre:
                        ref=entry; rearm_dir=-1; rearm_exp=i+rewin; rearm_min=i+1
                    else: rearm_dir=0; reidx=0
                    pos=0
        # RE-ENTRY: kalau armed & harga balik ke ref & tren msh dukung
        if pos==0 and pend==0 and rearm_dir!=0:
            if i>rearm_exp: rearm_dir=0; reidx=0
            elif rearm_dir>0 and i>=rearm_min and l[i]<=ref and c[i]>E[i]:
                entry=min(o[i],ref); eb=i; pos=1; reidx+=1; cursize=size_of(sizing,i,reidx)
                tp=entry*(1+tpq/100); slp=entry*(1-sl/100); rearm_dir=0
            elif rearm_dir<0 and i>=rearm_min and h[i]>=ref and c[i]<E[i]:
                entry=max(o[i],ref); eb=i; pos=-1; reidx+=1; cursize=size_of(sizing,i,reidx)
                tp=entry*(1-tpq/100); slp=entry*(1+sl/100); rearm_dir=0
        # sinyal baru
        if pos==0 and pend==0 and rearm_dir==0:
            bse=i-leb
            if long_sig[i] and not(led==1 and bse<cd): pend=1; reidx=0; cursize=size_of(sizing,i,0)
            elif short_sig[i] and not(led==-1 and bse<cd): pend=-1; reidx=0; cursize=size_of(sizing,i,0)
    t=pd.DataFrame(trades,columns=['eb','xb','dir','net','sz','ex'])
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

def oos(**kw):
    cut=int(n*0.70); _,t=run_qtp(**kw)
    return metrics(t[t['xb']<cut]),metrics(t[t['xb']>=cut])

if __name__=='__main__':
    from eng import run as eng_run
    TPa=np.full(n,TP_BASE); TPa[ap>TP_WALL]=TP_GENTLE; SLa=np.full(n,SL_V20)
    r0,_=eng_run(df,{'add_long':aL,'add_short':aS,'tp':TPa,'sl':SLa})
    print('BASE v20:',{k:r0[k] for k in ['ret','dd','wr','calmar','n']})

    print('\n=== A) QUICK-TP saja (no re-entry, static), sweep tpq ===')
    print(f"{'tpq':>5} | {'ret':>8}{'dd':>7}{'wr':>7}{'cal':>7}{'n':>6}")
    for tpq in [0.4,0.5,0.6,0.8,1.0]:
        r,t=run_qtp(tpq=tpq); py=peryear(t); ap_=all(v>0 for v in py.values())
        print(f'{tpq:>5} | {r["ret"]:>+8.0f}{r["dd"]:>7}{r["wr"]:>7}{r["calmar"]:>7}{r["n"]:>6}  allpos={ap_}')

    print('\n=== B) QUICK-TP 0.5% + RE-ENTRY, sizing static vs dynamic ===')
    print(f"{'sizing':>10}{'rewin':>6}{'maxre':>6} | {'ret':>8}{'dd':>7}{'wr':>7}{'cal':>7}{'n':>6}  allpos")
    for sz in ['static','volnorm','decay','voldecay']:
        for maxre in [1,2,3]:
            r,t=run_qtp(tpq=0.5,reentry=True,rewin=12,maxre=maxre,sizing=sz)
            py=peryear(t); aps=all(v>0 for v in py.values())
            print(f'{sz:>10}{12:>6}{maxre:>6} | {r["ret"]:>+8.0f}{r["dd"]:>7}{r["wr"]:>7}{r["calmar"]:>7}{r["n"]:>6}  {aps}')
