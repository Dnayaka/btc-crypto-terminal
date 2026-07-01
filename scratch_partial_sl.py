#!/usr/bin/env python3
"""Partial SL: exit posisi BERTAHAP di sisi rugi juga (bukan dump full di SL). Gabung dgn tiered-TP.
Ide: give-back-loser exit sebagian di rugi-kecil dulu -> avg loss < SL penuh -> DD turun.
Trade-off: winner yg dip (MAE -0.58%) kejual sebagian dini. fee 0.02%/fill. no re-entry. Validasi full+per-year+OOS."""
import numpy as np, pandas as pd
from eng import rsi,ema,atr,signals,DEF,run as eng_run
from bot_v20_funding import pbsig,TP_BASE,TP_GENTLE,TP_WALL,SL_V20
df=pd.read_csv('btc_15m_full.csv',parse_dates=['dt'])
o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float);c=df['close'].to_numpy(float)
n=len(c);year=df['dt'].dt.year.to_numpy()
R=rsi(c,DEF['rsi_len']);E=ema(c,DEF['ema_len']);A=atr(h,l,c,DEF['atr_len'])
ap=A/c*100;rng=np.maximum(h-l,1e-9);bodyr=np.abs(c-o)/rng
aL=pbsig(o,h,l,c,R,E,ap,bodyr,'long');aS=pbsig(o,h,l,c,R,E,ap,bodyr,'short')
TPa=np.full(n,TP_BASE);TPa[ap>TP_WALL]=TP_GENTLE;SLa=np.full(n,SL_V20)
LS,SS,_,_=signals(df,{**DEF,'add_long':aL,'add_short':aS},(o,h,l,c,R,E,A))

def run(tp_tiers=(1.0,2.0), tp_frac=0.5, sl_tiers=(0.6,1.2,1.9), sl_frac=(0.34,0.33,0.33), fee=0.0002):
    """jual tp_frac tiap tp_tier (atas); jual sl_frac[k] tiap sl_tier (bawah, level TERAKHIR=dump sisa)."""
    cd=DEF['cooldown'];start=max(DEF['warmup'],DEF['ema_len']+2)
    pos=0;e0=0;eb=0;led=0;leb=-10**9;tr=[]
    size=0.0; tsold=set(); ssold=set(); realized=0.0
    for i in range(start,n):
        if pos!=0:
            d=pos; done=False
            # --- SL tiers (adverse dulu) ---
            for k,lv in enumerate(sl_tiers):
                if k in ssold: continue
                lvl=e0*(1-lv/100) if d>0 else e0*(1+lv/100)
                reach=(l[i]<=lvl) if d>0 else (h[i]>=lvl)
                if reach:
                    fr = sl_frac[k] if k<len(sl_tiers)-1 else size  # tier terakhir dump sisa
                    fr=min(fr,size)
                    realized += fr*(((lvl/e0-1) if d>0 else (e0/lvl-1))) - fee*fr
                    size-=fr; ssold.add(k)
                    if size<=1e-9: tr.append((eb,i,d,realized));pos=0;led=d;leb=i;done=True;break
            if done: continue
            # --- TP tiers ---
            for k,lv in enumerate(tp_tiers):
                if k in tsold: continue
                lvl=e0*(1+lv/100) if d>0 else e0*(1-lv/100)
                reach=(h[i]>=lvl) if d>0 else (l[i]<=lvl)
                if reach and size>1e-9:
                    fr=min(tp_frac,size)
                    realized += fr*(((lvl/e0-1) if d>0 else (e0/lvl-1))) - fee*fr
                    size-=fr; tsold.add(k)
                    if size<=1e-9: tr.append((eb,i,d,realized));pos=0;led=d;leb=i;done=True;break
            if done: continue
        if pos==0:
            bse=i-leb
            if LS[i] and not(led==1 and bse<cd): pos=1;e0=o[i+1] if i+1<n else c[i];eb=i;size=1.0;tsold=set();ssold=set();realized=-fee
            elif SS[i] and not(led==-1 and bse<cd): pos=-1;e0=o[i+1] if i+1<n else c[i];eb=i;size=1.0;tsold=set();ssold=set();realized=-fee
    t=pd.DataFrame(tr,columns=['eb','xb','dir','net'])
    if len(t)==0:return dict(n=0),t
    eq=np.cumprod(1+t.net.to_numpy());pk=np.maximum.accumulate(eq);dd=((pk-eq)/pk).max()*100;ret=(eq[-1]-1)*100
    yy=year[t.xb.to_numpy()];py={int(y):(np.prod(1+g.net)-1)*100 for y,g in pd.DataFrame({'y':yy,'net':t.net}).groupby('y')}
    return dict(n=len(t),ret=round(ret),dd=round(dd,1),wr=round((t.net>0).mean()*100,1),
                cal=round(ret/dd,1) if dd>0 else 0,allpos=all(v>0 for v in py.values())),t

if __name__=='__main__':
    cut=int(n*0.70)
    def tc(t):
        te=t[t.xb>=cut]
        if len(te)==0:return 0
        eq=np.cumprod(1+te.net.to_numpy());pk=np.maximum.accumulate(eq);dd=((pk-eq)/pk).max()*100
        return round((eq[-1]-1)*100/dd,1) if dd>0 else 0
    print('BASE v20: ret+3327 dd11.0 wr64.3 cal303 | TEST21.9')
    print('2-tier TP only (SL penuh 1.9): ret1200 dd7.9 wr65 cal153 | TEST14.9  <- pembanding')
    print()
    print('=== 2-tier TP + PARTIAL SL (varian ladder) ===')
    print(f"{'sl ladder':>34} | {'ret':>6}{'dd':>6}{'wr':>6}{'cal':>6} | {'TEST':>5} allpos")
    for slt,slf,lbl in [
        ((0.6,1.2,1.9),(0.34,0.33,0.33),'25/25/50 @0.6/1.2/1.9'),
        ((1.0,1.5,1.9),(0.34,0.33,0.33),'@1.0/1.5/1.9'),
        ((0.8,1.9),(0.5,0.5),'50/50 @0.8/1.9'),
        ((1.2,1.9),(0.5,0.5),'50/50 @1.2/1.9'),
        ((0.5,1.0,1.5,1.9),(0.25,0.25,0.25,0.25),'25% x4 @0.5-1.9'),
    ]:
        r,t=run(tp_tiers=(1.0,2.0),tp_frac=0.5,sl_tiers=slt,sl_frac=slf)
        print(f'{lbl:>34} | {r["ret"]:>6}{r["dd"]:>6}{r["wr"]:>6}{r["cal"]:>6} | {tc(t):>5} {r["allpos"]}')
    print()
    print('=== banding: 4-tier TP + partial SL ===')
    r,t=run(tp_tiers=(1.0,1.5,2.0,2.5),tp_frac=0.25,sl_tiers=(0.6,1.2,1.9),sl_frac=(0.34,0.33,0.33))
    print(f'  4-tierTP+partialSL: {r} | TEST {tc(t)}')
