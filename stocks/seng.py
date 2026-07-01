#!/usr/bin/env python3
"""seng.py — stock daily backtester (IDX). Long-biased, no look-ahead, adverse-first intrabar
exits, realistic IDX fees. Pola exit faithful ke eng.py BTC (tervalidasi vs TV).

Sinyal entry PLUGGABLE via cf['mode']:
  'mr_rsi'    : mean-reversion (Connors-style) — RSI(n) oversold + uptrend (close>SMA_trend).
                Exit: close>SMA_exit (signal) / TP / SL / max_hold. -> WR tinggi (beli dip kualitas).
  'mr_bb'     : beli sentuh lower Bollinger di uptrend. Exit: kembali ke mid-band / TP / SL.
  'momentum'  : breakout — close tembus high N-bar + di atas SMA_trend (trend-follow). PnL > WR.
  'sma_pull'  : pullback ke SMA_fast yg naik dalam uptrend (SMA_trend naik).

Fundamental dipakai di level UNIVERSE (cuma trade saham likuid LQ45/IDX30) — bukan sinyal
historis (hindari look-ahead). Lihat fetch_stocks.UNIVERSE.

API:
  run(df, cf) -> (res, trades_df)              # 1 simbol
  run_portfolio({sym:df}, cf) -> (res, trades) # pooled cross-section (edge agregat)
"""
import numpy as np, pandas as pd

# ---------- indikator ----------
def rma(x,n):
    a=np.full(len(x),np.nan)
    if len(x)<n: return a
    a[n-1]=np.nanmean(x[:n])
    for i in range(n,len(x)): a[i]=(a[i-1]*(n-1)+x[i])/n
    return a
def rsi(c,n=14):
    d=np.diff(c,prepend=c[0]); up=np.where(d>0,d,0.0); dn=np.where(d<0,-d,0.0)
    ru=rma(up,n); rd=rma(dn,n); rs=np.where(rd==0,np.inf,ru/np.where(rd==0,1,rd))
    return np.where(rd==0,100.0,100.0-100.0/(1.0+rs))
def sma(x,n):
    a=np.full(len(x),np.nan); cs=np.cumsum(np.insert(x,0,0))
    if len(x)>=n: a[n-1:]=(cs[n:]-cs[:-n])/n
    return a
def ema(x,n):
    a=np.full(len(x),np.nan); k=2.0/(n+1)
    if len(x)<n: return a
    a[n-1]=np.mean(x[:n])
    for i in range(n,len(x)): a[i]=x[i]*k+a[i-1]*(1-k)
    return a
def atr(h,l,c,n=14):
    pc=np.roll(c,1); pc[0]=c[0]
    tr=np.maximum(h-l,np.maximum(np.abs(h-pc),np.abs(l-pc))); return rma(tr,n)
def rollmax(x,n):
    s=pd.Series(x); return s.rolling(n).max().to_numpy()
def rollmin(x,n):
    s=pd.Series(x); return s.rolling(n).min().to_numpy()

DEF=dict(
    mode='mr_rsi',
    # mean-reversion
    rsi_len=3, rsi_buy=15.0, rsi_exit=60.0, sma_trend=200, sma_exit=5,
    rsi2_or=0.0, req_sma50_rising=False, sma50_rise_win=5,   # gabungan trigger + filter uptrend-asli (riset workflow)
    # bollinger
    bb_len=20, bb_k=2.0,
    # momentum/breakout
    bo_len=20, sma_fast=50,
    # exit umum
    tp=0.0, sl=8.0, max_hold=10, use_trail=False, trail_atr=3.0, atr_len=14,
    # filter likuiditas/regime
    min_close=50.0, vol_ma=20, min_volval=0.0,   # min nilai transaksi (close*vol) rata2
    # biaya IDX & sizing
    fee_buy=0.0015, fee_sell=0.0025, warmup=210,
)

def indicators(df,cf):
    # C1: indikator pakai harga BACK-ADJUSTED (adjclose) -> cegah sinyal "oversold" PALSU di bar ex-div/split.
    # Scale semua OHLC by faktor adjclose/close (bar TERAKHIR adjclose==close -> harga display tetap raw).
    cr=df['close'].to_numpy(float)
    if 'adjclose' in df.columns:
        ac=df['adjclose'].to_numpy(float); f=np.where(cr>0, ac/cr, 1.0)
        o=df['open'].to_numpy(float)*f; h=df['high'].to_numpy(float)*f; l=df['low'].to_numpy(float)*f; c=ac
    else:
        o=df['open'].to_numpy(float); h=df['high'].to_numpy(float); l=df['low'].to_numpy(float); c=cr
    v=df['volume'].to_numpy(float)
    R=rsi(c,cf['rsi_len']); R2=rsi(c,2); St=sma(c,cf['sma_trend']); Se=sma(c,cf['sma_exit'])
    Sf=sma(c,cf['sma_fast']); A=atr(h,l,c,cf['atr_len'])
    bm=sma(c,cf['bb_len']); bsd=pd.Series(c).rolling(cf['bb_len']).std(ddof=0).to_numpy()
    bl=bm-cf['bb_k']*bsd; bu=bm+cf['bb_k']*bsd
    hh=rollmax(h,cf['bo_len']); volma=sma(c*v,cf['vol_ma'])
    return dict(o=o,h=h,l=l,c=c,v=v,R=R,R2=R2,St=St,Se=Se,Sf=Sf,A=A,bm=bm,bl=bl,bu=bu,hh=hh,volval=volma)

def entry_exit(df,cf,ind):
    c=ind['c']; o=ind['o']; R=ind['R']; St=ind['St']; Se=ind['Se']; Sf=ind['Sf']
    n=len(c)
    uptrend = c>St                        # regime kualitas: di atas SMA200
    liq = (c>=cf['min_close'])
    if cf['min_volval']>0: liq &= (ind['volval']>=cf['min_volval'])
    mode=cf['mode']; ent=np.zeros(n,bool); ex=np.zeros(n,bool)
    if mode=='mr_rsi':
        deep = (R<cf['rsi_buy'])
        if cf.get('rsi2_or',0)>0: deep = deep | (ind['R2']<cf['rsi2_or'])   # union trigger oversold dalam
        ent = deep & uptrend & liq
        if cf.get('req_sma50_rising'):                                       # cuma beli dip saat uptrend ASLI (SMA50 naik)
            Sf=ind['Sf']; ent = ent & (Sf>np.roll(Sf,cf.get('sma50_rise_win',5)))
        ex  = (c>Se) | (R>cf['rsi_exit'])         # keluar saat pulih
    elif mode=='mr_bb':
        ent = (ind['l']<=ind['bl']) & uptrend & liq
        ex  = (c>=ind['bm'])
    elif mode=='momentum':
        hh1=np.roll(ind['hh'],1)
        ent = (c>hh1) & uptrend & liq
        ex  = (c<Sf)                               # keluar saat tutup di bawah SMA_fast
    elif mode=='sma_pull':
        Sf1=np.roll(Sf,5)
        ent = (c>St) & (Sf>Sf1) & (ind['l']<=Sf) & (c>o) & liq   # pullback ke SMA_fast naik
        ex  = (c<Sf) | (R>cf['rsi_exit'])
    ent[:cf['warmup']]=False; ex[:cf['warmup']]=False
    # hook tambahan (AND filter / OR add) utk search
    if cf.get('extra_long') is not None: ent &= np.asarray(cf['extra_long'],bool)
    return ent, ex

def run(df,cfg=None):
    cf=dict(DEF); cf.update(cfg or {})
    ind=indicators(df,cf); o,h,l,c,A=ind['o'],ind['h'],ind['l'],ind['c'],ind['A']
    ent,ex=entry_exit(df,cf,ind); n=len(c)
    fb,fs=cf['fee_buy'],cf['fee_sell']; start=max(cf['warmup'],cf['sma_trend']+2)
    tp=cf['tp']; sl=cf['sl']; mh=cf['max_hold']; use_tr=cf['use_trail']; tatr=cf['trail_atr']
    pos=0; entry=0.0; entry_bar=0; tpx=slx=0.0; hi=0.0; trail=np.nan; pending=False
    trades=[]
    dts=df['dt'].to_numpy() if 'dt' in df else np.arange(n)
    for i in range(start,n):
        # 1) fill pending di open[i]
        if pending and pos==0:
            entry=o[i]; entry_bar=i; pos=1
            tpx=entry*(1+tp/100.0) if tp>0 else np.inf
            slx=entry*(1-sl/100.0) if sl>0 else 0.0
            hi=h[i]; trail=np.nan; pending=False
        # 2) kelola exit bar i (adverse-first: stop dulu, baru TP, baru sinyal-exit di close)
        if pos!=0:
            stop = slx if np.isnan(trail) else max(slx,trail)
            hit_sl = l[i]<=stop and stop>0
            hit_tp = h[i]>=tpx
            reason=None; px=0.0
            if hit_sl: px=min(o[i],stop) if o[i]<stop else stop; reason='SL' if np.isnan(trail) or stop<=slx else 'Trail'
            elif hit_tp: px=max(o[i],tpx) if o[i]>tpx else tpx; reason='TP'
            if reason is None:
                # update trailing utk bar berikut
                hi=max(hi,h[i])
                if use_tr and not np.isnan(A[i]):
                    nt=hi-tatr*A[i]; trail=nt if np.isnan(trail) else max(trail,nt)
                # sinyal-exit dievaluasi di CLOSE -> eksekusi di close bar ini
                if ex[i]: px=c[i]; reason='Sig'
                elif mh>0 and (i-entry_bar)>=mh: px=c[i]; reason='Time'
            if reason:
                ret=(px/entry)*(1-fs)/(1+fb)-1.0     # net pp termasuk fee beli+jual
                trades.append((entry_bar,i,entry,px,ret,reason,i-entry_bar))
                pos=0; trail=np.nan
        # 3) sinyal entry di close[i] -> pending utk open[i+1]
        if pos==0 and not pending and ent[i]:
            pending=True
    t=pd.DataFrame(trades,columns=['eb','xb','entry','exit','net','reason','hold'])
    return _metrics(t,df), t

def _metrics(t,df=None):
    if len(t)==0: return dict(n=0,ret=0,dd=0,wr=0,calmar=0,pf=0,avg=0,hold=0)
    eq=np.cumprod(1+t['net'].to_numpy()); peak=np.maximum.accumulate(eq)
    dd=((peak-eq)/peak).max()*100; ret=(eq[-1]-1)*100; wr=(t['net']>0).mean()*100
    gp=t.loc[t['net']>0,'net'].sum(); gl=-t.loc[t['net']<0,'net'].sum()
    pf=gp/gl if gl>0 else np.inf
    return dict(n=len(t),ret=round(ret,1),dd=round(dd,2),wr=round(wr,2),
                calmar=round(ret/dd,2) if dd>0 else 0,pf=round(pf,2),
                avg=round(t['net'].mean()*100,3),hold=round(t['hold'].mean(),1))

def run_portfolio(data, cfg=None, lev=1.0):
    """Pool semua trade lintas simbol (equal-weight, 1 posisi/sinyal). Edge AGREGAT universe.
    Equity = compound semua trade diurut waktu keluar (proxy; bukan portfolio paralel penuh)."""
    allt=[]
    for sym,df in data.items():
        if df is None or len(df)<260: continue
        _,t=run(df,cfg)
        if len(t):
            t=t.copy(); t['sym']=sym
            t['xdt']=df['dt'].to_numpy()[t['xb'].to_numpy()]
            allt.append(t)
    if not allt: return dict(n=0,ret=0,dd=0,wr=0,calmar=0,pf=0,avg=0,hold=0), pd.DataFrame()
    T=pd.concat(allt).sort_values('xdt').reset_index(drop=True)
    res=_metrics(T)
    # per-tahun (berdasar tanggal keluar)
    yrs=pd.to_datetime(T['xdt']).dt.year
    res['per_year']={int(y):round((np.prod(1+g['net'].to_numpy())-1)*100,1) for y,g in T.groupby(yrs)}
    res['n_sym']=T['sym'].nunique()
    return res, T

if __name__=='__main__':
    import glob,os
    HERE=os.path.dirname(os.path.abspath(__file__)); DATA=os.path.join(HERE,"data")
    files=glob.glob(os.path.join(DATA,"*.JK.csv"))
    print(f"load {len(files)} saham...")
    data={}
    for f in files:
        sym=os.path.basename(f)[:-4]
        try: data[sym]=pd.read_csv(f,parse_dates=['dt'])
        except Exception: pass
    for mode in ['mr_rsi','mr_bb','momentum','sma_pull']:
        res,_=run_portfolio(data,{'mode':mode})
        print(f"  {mode:9s}: n={res['n']:5d} WR={res['wr']:.1f}% ret={res['ret']:+.0f}% DD={res['dd']:.1f}% PF={res['pf']} avg={res['avg']}% hold={res['hold']}d")
