#!/usr/bin/env python3
"""eng.py — clean, faithful v14.2 backtester (rebuilt). Replicates the v17/v14.2 pine:
RSI(14) breakout 82/20 + candle + EMA200 + ATR/body/emadist filters, TP2.0/SL1.9, cooldown6,
adverse-first intrabar exits, signal@close -> fill next open, fee 0.02%/side, 1x.
Hooks for feature search: extra_long/extra_short masks, regime-conditioned tp/sl (arrays),
extra entry signals, breakeven, time-stop, trailing. Validated vs the v14.2 TV export.
"""
import numpy as np, pandas as pd

def rma(x, n):
    a = np.full(len(x), np.nan)
    if len(x) < n: return a
    a[n-1] = np.nanmean(x[:n])
    for i in range(n, len(x)):
        a[i] = (a[i-1]*(n-1) + x[i]) / n
    return a

def rsi(close, n=14):
    d = np.diff(close, prepend=close[0])
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    ru = rma(up, n); rd = rma(dn, n)
    rs = np.where(rd == 0, np.inf, ru/np.where(rd==0,1,rd))
    return np.where(rd == 0, 100.0, 100.0 - 100.0/(1.0+rs))

def ema(x, n):
    a = np.full(len(x), np.nan); k = 2.0/(n+1)
    if len(x) < n: return a
    a[n-1] = np.mean(x[:n])
    for i in range(n, len(x)):
        a[i] = x[i]*k + a[i-1]*(1-k)
    return a

def atr(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h-l, np.maximum(np.abs(h-pc), np.abs(l-pc)))
    return rma(tr, n)

DEF = dict(ob=79.0, os=23.0, gap=3.0, rsi_len=14, ema_len=200, ema_buf=0.20, atr_len=14,
           max_atr=1.0, atr_floor=0.2, body_min=0.3, long_emadist=1.5,
           tp=2.0, sl=1.9, cooldown=6, fee=0.0002, lev=1.0, warmup=300,
           use_trail=True, trail_mult=2.0, trail_min=0.5, trail_max=2.0, trail_act=2.5,
           be_trigger=0.0, max_hold=0)

def indicators(df, cf):
    o=df['open'].to_numpy(float); h=df['high'].to_numpy(float)
    l=df['low'].to_numpy(float); c=df['close'].to_numpy(float)
    r=rsi(c,cf['rsi_len']); e=ema(c,cf['ema_len']); a=atr(h,l,c,cf['atr_len'])
    return o,h,l,c,r,e,a

def signals(df, cf, ind=None):
    o,h,l,c,r,e,a = ind if ind else indicators(df, cf)
    n=len(c)
    atr_pct = a/c*100.0
    rng = h-l
    body = np.where(rng>0, np.abs(c-o)/np.where(rng>0,rng,1), 0.0)
    emadist = (c-e)/e*100.0
    long_lvl = cf['ob']+cf['gap']; short_lvl = cf['os']-cf['gap']
    xover = (r>long_lvl) & (np.roll(r,1)<=long_lvl)
    xunder = (r<short_lvl) & (np.roll(r,1)>=short_lvl)
    xover[0]=False; xunder[0]=False
    cl = c>o; cs = c<o
    el = c > e*(1+cf['ema_buf']/100.0); es = c < e*(1-cf['ema_buf']/100.0)
    ac = (cf['max_atr']<=0) | (atr_pct<=cf['max_atr'])
    af = (cf['atr_floor']<=0) | (atr_pct>=cf['atr_floor'])
    bo = (cf['body_min']<=0) | (body>=cf['body_min'])
    ld = (cf['long_emadist']<=0) | (emadist>=cf['long_emadist'])
    long_sig = xover & cl & el & ac & af & bo & ld
    short_sig = xunder & cs & es & ac & af & bo
    # AND-filter hook (subtract trades) -- NOTE: proven to only cut +EV; use sparingly
    if 'extra_long' in cf and cf['extra_long'] is not None:  long_sig &= np.asarray(cf['extra_long'],bool)
    if 'extra_short' in cf and cf['extra_short'] is not None: short_sig &= np.asarray(cf['extra_short'],bool)
    # OR-add hook (ADD new entries from a complementary signal the agent computes)
    if 'add_long' in cf and cf['add_long'] is not None:   long_sig = long_sig | np.asarray(cf['add_long'],bool)
    if 'add_short' in cf and cf['add_short'] is not None: short_sig = short_sig | np.asarray(cf['add_short'],bool)
    return long_sig, short_sig, atr_pct, emadist

def run(df, cfg=None):
    cf = dict(DEF); cf.update(cfg or {})
    ind = indicators(df, cf)
    o,h,l,c,r,e,a = ind
    n=len(c)
    long_sig, short_sig, atr_pct, emadist = signals(df, cf, ind)
    # per-bar tp/sl (allow regime arrays)
    tp_arr = np.full(n, cf['tp'], float) if np.isscalar(cf['tp']) else np.asarray(cf['tp'],float)
    sl_arr = np.full(n, cf['sl'], float) if np.isscalar(cf['sl']) else np.asarray(cf['sl'],float)
    fee=cf['fee']; cd=cf['cooldown']; start=max(cf['warmup'], cf['ema_len']+2)
    use_tr=cf['use_trail']; tmult=cf['trail_mult']; tmin=cf['trail_min']; tmax=cf['trail_max']; tact=cf['trail_act']
    bet=cf['be_trigger']
    pos=0; entry=0.0; entry_bar=0; tp=sl=0.0; tpct=spct=0.0
    last_exit_dir=0; last_exit_bar=-10**9
    pending=0; trades=[]
    mfe=mae=0.0; hi=lo=0.0; trail=np.nan; gap=0.0; be_done=False
    for i in range(start, n):
        # 1) fill pending at open[i]
        if pending!=0 and pos==0:
            entry=o[i]; entry_bar=i; pos=pending
            tpct=tp_arr[i-1]; spct=sl_arr[i-1]
            if pos>0:
                tp=entry*(1+tpct/100.0) if tpct>0 else np.inf; sl=entry*(1-spct/100.0) if spct>0 else 0.0
            else:
                tp=entry*(1-tpct/100.0) if tpct>0 else 0.0; sl=entry*(1+spct/100.0) if spct>0 else np.inf
            gap=max(tmin*entry/100.0, min(tmax*entry/100.0, a[i]*tmult))
            mfe=mae=0.0; hi=h[i]; lo=l[i]; trail=np.nan; be_done=False; pending=0
        # 2) manage exit on bar i: EXIT CHECK FIRST (stop/trail from PRIOR bars; no intrabar look-ahead)
        if pos!=0:
            if pos>0:
                mfe=max(mfe,(h[i]-entry)/entry*100.0); mae=min(mae,(l[i]-entry)/entry*100.0)
                stop = sl if np.isnan(trail) else max(sl,trail)
                hit_sl = l[i]<=stop; hit_tp = h[i]>=tp
                ex=None; px=0.0
                if hit_sl:  px = min(o[i],stop) if o[i]<stop else stop; ex=('Trail' if (not np.isnan(trail) and stop>sl) else 'SL')
                elif hit_tp: px = max(o[i],tp) if o[i]>tp else tp; ex='TP'
                if ex:
                    ret = (px/entry-1) - 2*fee
                    trades.append((entry_bar,i,pos,entry,px,ret,ex,mfe,mae))
                    pos=0; last_exit_dir=1; last_exit_bar=i
                else:  # still in pos -> update hi/trail/BE for NEXT bar
                    hi=max(hi,h[i])
                    if bet>0 and not be_done and (hi-entry)/entry*100.0>=bet: sl=max(sl,entry); be_done=True
                    if use_tr and (hi-entry)>=tact*entry/100.0:
                        nt=hi-gap; trail=nt if np.isnan(trail) else max(trail,nt)
            else:
                mfe=max(mfe,(entry-l[i])/entry*100.0); mae=min(mae,(entry-h[i])/entry*100.0)
                stop = sl if np.isnan(trail) else min(sl,trail)
                hit_sl = h[i]>=stop; hit_tp = l[i]<=tp
                ex=None; px=0.0
                if hit_sl: px = max(o[i],stop) if o[i]>stop else stop; ex=('Trail' if (not np.isnan(trail) and stop<sl) else 'SL')
                elif hit_tp: px = min(o[i],tp) if o[i]<tp else tp; ex='TP'
                if ex:
                    ret = (entry/px-1) - 2*fee
                    trades.append((entry_bar,i,pos,entry,px,ret,ex,mfe,mae))
                    pos=0; last_exit_dir=-1; last_exit_bar=i
                else:
                    lo=min(lo,l[i])
                    if bet>0 and not be_done and (entry-lo)/entry*100.0>=bet: sl=min(sl,entry); be_done=True
                    if use_tr and (entry-lo)>=tact*entry/100.0:
                        nt=lo+gap; trail=nt if np.isnan(trail) else min(trail,nt)
            # time-stop
            if pos!=0 and cf['max_hold']>0 and (i-entry_bar)>=cf['max_hold']:
                d=1 if pos>0 else -1                       # FIX: capture dir BEFORE pos=0 (dulu last_exit_dir selalu -1)
                px=c[i]; ret=((px/entry-1) if pos>0 else (entry/px-1)) - 2*fee
                trades.append((entry_bar,i,pos,entry,px,ret,'time',mfe,mae))
                pos=0; last_exit_dir=d; last_exit_bar=i
        # 3) signal on bar i close -> pending next open
        if pos==0 and pending==0:
            bse = i - last_exit_bar
            cdL = not (last_exit_dir==1 and bse<cd)
            cdS = not (last_exit_dir==-1 and bse<cd)
            if long_sig[i] and cdL: pending=1
            elif short_sig[i] and cdS: pending=-1
    t=pd.DataFrame(trades, columns=['entry_bar','exit_bar','dir','entry','exit','net','reason','mfe','mae'])
    if len(t)==0:
        return dict(n=0,ret=0,dd=0,wr=0,calmar=0,pf=0), t
    eq=np.cumprod(1+cf['lev']*t['net'].to_numpy())
    peak=np.maximum.accumulate(eq); dd=((peak-eq)/peak).max()*100
    ret=(eq[-1]-1)*100; wr=(t['net']>0).mean()*100
    gp=t.loc[t['net']>0,'net'].sum(); gl=-t.loc[t['net']<0,'net'].sum()
    pf=gp/gl if gl>0 else np.inf
    res=dict(n=len(t),ret=round(ret,1),dd=round(dd,2),wr=round(wr,2),
             calmar=round(ret/dd,1) if dd>0 else 0,pf=round(pf,2),
             nl=int((t['dir']>0).sum()),ns=int((t['dir']<0).sum()))
    return res, t

def per_year(df, t, lev=1.0):
    if len(t)==0: return {}
    yrs=df['dt'].dt.year.to_numpy()[t['exit_bar'].to_numpy()]
    g=pd.DataFrame({'y':yrs,'net':t['net'].to_numpy()})
    return {int(y):round((np.prod(1+lev*gg['net'].to_numpy())-1)*100,1) for y,gg in g.groupby('y')}

if __name__=='__main__':
    df=pd.read_csv('btc_15m_full.csv', parse_dates=['dt'])
    res,t=run(df)
    print('v14.2 base:', res)
    print('per-year:', per_year(df,t))
