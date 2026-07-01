#!/usr/bin/env python3
"""ara.py — engine ARA-hunting low-cap IDX. Strategi = beli SETUP pra-ledakan (fillable),
BUKAN ngejar ARA yg udah lock. Fill REALISTIS: entri next-open, SKIP kalau gap lock-ARA
(tak bisa beli), slippage haircut, stop ARB-aware. Long-only, daily.

Pakai: setup_mask (boolean per bar dari 'saringan') -> backtest_setup(df, mask, cf) -> trades.
Fitur bantu utk nyusun saringan ada di features(df)."""
import numpy as np, pandas as pd
import seng

def ara_limit(price):
    """Batas Auto-Reject Atas (approx simetris post-2021)."""
    return 0.35 if price<200 else (0.25 if price<5000 else 0.20)

ADEF=dict(tp=12.0, sl=8.0, max_hold=4, trail_act=8.0, trail_giveback=5.0, use_trail=True,
          slip=0.005, fee_buy=0.0015, fee_sell=0.0025, warmup=60,
          skip_locked=True)   # skip entri kalau next-open gap lock-ARA (tak fillable)

def features(df):
    """Fitur low-cap utk saringan: volume surge, range/consolidation, prior-ARA, posisi harga."""
    o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float)
    c=df['close'].to_numpy(float);v=df['volume'].to_numpy(float)
    pc=np.roll(c,1);pc[0]=c[0]; ret=c/pc-1.0
    vma20=seng.sma(v,20); vsurge=v/np.where(vma20>0,vma20,np.nan)         # lonjakan volume vs MA20
    volval=c*v                                                            # nilai transaksi
    hh20=pd.Series(h).rolling(20).max().to_numpy(); breakout=c>np.roll(hh20,1)  # tembus high 20-hari
    rng20=(pd.Series(h).rolling(20).max()-pd.Series(l).rolling(20).min()).to_numpy()/c  # lebar range (konsolidasi kalau kecil)
    lim=np.array([ara_limit(p) for p in pc]); is_ara=ret>=lim*0.985       # hari nutup ~mentok atas
    prior_ara=pd.Series(is_ara.astype(float)).rolling(10).sum().to_numpy() # #ARA 10 hari terakhir (momentum bandar)
    sma5=seng.sma(c,5); sma20=seng.sma(c,20); above=(c>sma20)
    rsi=seng.rsi(c,14)
    up_streak=np.zeros(len(c))
    for i in range(1,len(c)): up_streak[i]=up_streak[i-1]+1 if c[i]>c[i-1] else 0
    return dict(o=o,h=h,l=l,c=c,v=v,ret=ret,vsurge=vsurge,volval=volval,breakout=breakout,
                rng20=rng20,is_ara=is_ara,prior_ara=prior_ara,sma5=sma5,sma20=sma20,above=above,
                rsi=rsi,up_streak=up_streak,hh20=hh20)

def backtest_setup(df, mask, cfg=None):
    cf=dict(ADEF); cf.update(cfg or {})
    o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float);c=df['close'].to_numpy(float)
    n=len(c); mask=np.asarray(mask,bool); fb,fs,slip=cf['fee_buy'],cf['fee_sell'],cf['slip']
    tp,sl,mh=cf['tp'],cf['sl'],cf['max_hold']; trail_act=cf['trail_act']; gb=cf['trail_giveback']
    pos=0;entry=0.0;eb=0;hi=0.0;trail=np.nan;pending=False;trades=[];skipped=0
    for i in range(cf['warmup'],n):
        if pending and pos==0:
            pc=c[i-1]; lim=ara_limit(pc)
            gap=o[i]/pc-1.0
            locked = cf['skip_locked'] and (gap>=lim*0.985) and ((h[i]-l[i])/max(o[i],1e-9)<0.005)
            if locked: skipped+=1; pending=False     # ARA lock di open -> tak bisa beli, batal
            else:
                entry=o[i]*(1+slip); eb=i; pos=1; hi=h[i]; trail=np.nan; pending=False
        if pos!=0:
            stop=entry*(1-sl/100.0) if sl>0 else 0.0
            if not np.isnan(trail): stop=max(stop,trail)
            tpx=entry*(1+tp/100.0) if tp>0 else np.inf
            reason=None;px=0.0
            if l[i]<=stop and stop>0: px=min(o[i],stop)*(1-slip); reason='SL'
            elif h[i]>=tpx: px=tpx*(1-slip); reason='TP'
            if reason is None:
                hi=max(hi,h[i])
                if cf['use_trail'] and (hi/entry-1)*100>=trail_act:
                    nt=hi*(1-gb/100.0); trail=nt if np.isnan(trail) else max(trail,nt)
                if mh>0 and (i-eb)>=mh: px=c[i]*(1-slip); reason='Time'
            if reason:
                ret=(px/entry)*(1-fs)/(1+fb)-1.0
                trades.append((eb,i,entry,px,ret,reason,i-eb)); pos=0;trail=np.nan
        if pos==0 and not pending and mask[i]: pending=True
    t=pd.DataFrame(trades,columns=['eb','xb','entry','exit','net','reason','hold'])
    return t, skipped

def stats(t):
    if len(t)==0: return dict(n=0,wr=0,mean=0,pf=0,tot=0,med=0)
    x=t['net'].to_numpy();gp=x[x>0].sum();gl=-x[x<0].sum()
    return dict(n=len(x),wr=round((x>0).mean()*100,1),mean=round(x.mean()*100,3),
                pf=round(gp/gl,2) if gl>0 else 99.9,tot=round(x.sum()*100,1),med=round(np.median(x)*100,3))
