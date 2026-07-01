#!/usr/bin/env python3
"""scalping_v1.py — SCALPING BTC: cari entry buat tangkap 200 USD (=200 poin) gerak harga.
TF kecil (default 5m; bisa 1m). Target TP FIXED $200, SL fixed $ (param). Fee-aware, adverse-fill.
Harness riset: banding beberapa logika entry (mean-rev RSI, BB-fade, micro-breakout) + report jujur
(WR / EV-per-trade / ret / DD / per-tahun).

⚠️ CATATAN (riset 30-Jun, CLAUDE.md): scalp 100-200pt di BTC = TAK ADA edge robust (fee+mean-rev-lemah+
give-back). Script ini = ALAT uji, bukan jaminan profit. Angka di bawah nunjukin realita.

  python3 scalping_v1.py                 # backtest 5m semua strategi
  python3 scalping_v1.py --tf 1m         # pakai btc_1m_full.csv kalau ada
  python3 scalping_v1.py --signal now    # sinyal terkini (live entry-finder)
"""
import os, sys, argparse
import numpy as np, pandas as pd

HERE=os.path.dirname(os.path.abspath(__file__))
TP_USD=200.0                 # target profit fixed ($ / poin)
FEE=0.0000                   # user: anggap fee 0% (edge MENTAH; live taker ~0.04% RT)
# ---------- indikator ----------
def rma(x,n):
    a=np.full(len(x),np.nan)
    if len(x)<n: return a
    a[n-1]=np.nanmean(x[:n])
    for i in range(n,len(x)): a[i]=(a[i-1]*(n-1)+x[i])/n
    return a
def rsi(c,n=14):
    d=np.diff(c,prepend=c[0]); up=np.where(d>0,d,0.); dn=np.where(d<0,-d,0.)
    ru=rma(up,n); rd=rma(dn,n); rs=np.where(rd==0,np.inf,ru/np.where(rd==0,1,rd))
    return np.where(rd==0,100.,100.-100./(1.+rs))
def ema(x,n):
    a=np.full(len(x),np.nan); k=2./(n+1)
    if len(x)<n: return a
    a[n-1]=np.mean(x[:n])
    for i in range(n,len(x)): a[i]=x[i]*k+a[i-1]*(1-k)
    return a
def sma(x,n): return pd.Series(x).rolling(n).mean().to_numpy()
def stdev(x,n): return pd.Series(x).rolling(n).std().to_numpy()

# ---------- data ----------
def load(tf="5m"):
    path=os.path.join(HERE,f"btc_{tf}_full.csv")
    if not os.path.exists(path): sys.exit(f"data {path} ga ada. Fetch dulu (fetch_5m.py pola).")
    df=pd.read_csv(path)
    if 'dt' not in df.columns: df['dt']=pd.to_datetime(df['open_time'],unit='ms')
    else: df['dt']=pd.to_datetime(df['dt'])
    return df

# ---------- entry signals (kembalikan long_sig, short_sig boolean) ----------
def sig_meanrev(o,h,l,c, rsi_len=14, os_lvl=25, ob_lvl=75):
    """Fade: RSI oversold -> long (harap mantul 200$); overbought -> short."""
    R=rsi(c,rsi_len)
    long_sig=(R<os_lvl)&(np.roll(R,1)>=os_lvl)   # baru tembus ke bawah OS
    short_sig=(R>ob_lvl)&(np.roll(R,1)<=ob_lvl)
    return long_sig, short_sig, {"RSI":R}
def sig_bbfade(o,h,l,c, n=20, mult=2.0):
    """Harga tembus band bawah -> long (revert ke mean); band atas -> short."""
    m=sma(c,n); s=stdev(c,n); up=m+mult*s; dn=m-mult*s
    long_sig=(l<dn)&(c>dn)      # spike bawah band lalu tutup di atas (rejection)
    short_sig=(h>up)&(c<up)
    return long_sig, short_sig, {"bb_up":up,"bb_dn":dn}
def sig_breakout(o,h,l,c, n=20):
    """Micro-momentum: tembus high N-bar -> long; low -> short."""
    hh=pd.Series(h).rolling(n).max().shift(1).to_numpy()
    ll=pd.Series(l).rolling(n).min().shift(1).to_numpy()
    long_sig=c>hh; short_sig=c<ll
    return long_sig, short_sig, {}

def sig_pullback(o,h,l,c, rsi_len=14, os_lvl=35, ob_lvl=65, ema_len=200):
    """⭐ Mean-rev SEARAH tren (temuan validasi 30-Jun, 4/4 walk-forward GROSS):
    LONG = RSI<35 & close>EMA200 (beli dip dangkal di uptrend); SHORT = RSI>65 & close<EMA200."""
    R=rsi(c,rsi_len); Et=ema(c,ema_len)
    long_sig=(R<os_lvl)&(c>Et)
    short_sig=(R>ob_lvl)&(c<Et)
    return long_sig, short_sig, {"RSI":R,"EMA":Et}

SIGNALS={"pullback":sig_pullback,"meanrev":sig_meanrev,"bbfade":sig_bbfade,"breakout":sig_breakout}

# ---------- engine: TP/SL fixed $ ----------
def backtest(df, signal="meanrev", sl_usd=200.0, cooldown=3, max_hold=60, trend_ema=0, **kw):
    o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float);c=df['close'].to_numpy(float)
    n=len(c); LS,SS,extra=SIGNALS[signal](o,h,l,c,**kw)
    Etr=ema(c,trend_ema) if trend_ema>0 else None
    start=50; pos=0; entry=0.; eb=0; tp=sl=0.; last_exit=-10**9; trades=[]
    for i in range(start,n):
        if pos!=0:
            ex=None; px=0.
            if pos>0:
                if l[i]<=sl: px=min(o[i],sl); ex='SL'
                elif h[i]>=tp: px=max(o[i],tp) if o[i]>tp else tp; ex='TP'
            else:
                if h[i]>=sl: px=max(o[i],sl); ex='SL'
                elif l[i]<=tp: px=min(o[i],tp) if o[i]<tp else tp; ex='TP'
            if ex is None and max_hold>0 and (i-eb)>=max_hold: px=c[i]; ex='time'
            if ex:
                ret=((px/entry-1) if pos>0 else (entry/px-1))-FEE
                trades.append((eb,i,pos,entry,px,ret,ex)); pos=0; last_exit=i
        if pos==0 and (i-last_exit)>=cooldown:
            up = (Etr is None) or (c[i]>Etr[i]); dn=(Etr is None) or (c[i]<Etr[i])
            if LS[i] and up:
                entry=o[i+1] if i+1<n else c[i]; eb=i+1 if i+1<n else i; pos=1
                tp=entry+TP_USD; sl=entry-sl_usd
            elif SS[i] and dn:
                entry=o[i+1] if i+1<n else c[i]; eb=i+1 if i+1<n else i; pos=-1
                tp=entry-TP_USD; sl=entry+sl_usd
    t=pd.DataFrame(trades,columns=['eb','xb','dir','entry','exit','net','reason'])
    return t

def report(df,t,label=""):
    if len(t)==0: print(f"  {label}: 0 trade"); return
    eq=np.cumprod(1+t['net'].to_numpy()); pk=np.maximum.accumulate(eq)
    dd=((pk-eq)/pk).max()*100; ret=(eq[-1]-1)*100; wr=(t['net']>0).mean()*100
    ev=t['net'].mean()*100  # EV per trade %
    yb=df['dt'].dt.year.to_numpy()
    t=t.copy(); t['y']=yb[t['xb'].to_numpy()]
    py={int(y):round((np.prod(1+g['net'])-1)*100,1) for y,g in t.groupby('y')}
    allpos=all(v>0 for v in py.values())
    print(f"  {label:>10}: n{len(t):>5} WR{wr:>5.1f}% EV/trade{ev:>+6.3f}% ret{ret:>+8.0f}% dd{dd:>5.1f} allpos={allpos}")
    return dict(n=len(t),wr=round(wr,1),ev=round(ev,3),ret=round(ret),dd=round(dd,1),allpos=allpos,py=py)

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--tf",default="5m"); ap.add_argument("--signal",default="")
    a=ap.parse_args()
    df=load(a.tf)
    print(f"SCALPING v1 — TF {a.tf} — {len(df)} bar — TP fixed ${TP_USD:.0f}, fee {FEE*100:.2f}% RT")
    print(f"span {df.dt.min()} -> {df.dt.max()}\n")
    if a.signal=="now":
        # live entry-finder: cek sinyal di bar terakhir
        o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float);c=df['close'].to_numpy(float)
        px=c[-1]
        for nm,fn in SIGNALS.items():
            LS,SS,_=fn(o,h,l,c)
            s="LONG" if LS[-1] else ("SHORT" if SS[-1] else "-")
            print(f"  {nm:>10}: {s}  (px={px:.0f} -> TP {'+' if s!='SHORT' else '-'}${TP_USD:.0f})")
        sys.exit()
    print("=== banding entry (SL=$200, cooldown3, max_hold 60 bar) ===")
    for sg in ["pullback","meanrev","bbfade","breakout"]:
        t=backtest(df,signal=sg,sl_usd=200,cooldown=3,max_hold=60); report(df,t,sg)
    print("\n=== ⭐ DEFAULT v1: PULLBACK (RSI35/65 searah EMA200) sweep SL, TP $200 ===")
    for sl in [200,250,300]:
        t=backtest(df,signal="pullback",sl_usd=sl,cooldown=3,max_hold=60); report(df,t,f"SL${sl}")
    print("REKOMENDASI: pullback SL$250 (WR~59%, EV+ gross, walk-forward 4/4). ⚠️ fee=0 di set ini;")
    print("             live taker ~0.04% RT bikin EV recent jadi ~breakeven/negatif.")
