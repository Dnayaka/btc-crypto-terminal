#!/usr/bin/env python3
"""mflow.py — indikator MONEY FLOW / akumulasi-distribusi dari OHLCV (REAL, bukan broksum berbayar).
MFI (money flow index), CMF (Chaikin money flow), buy/sell pressure % (volume hijau vs merah), OBV-trend.
Proxy bandarmology yang sah & terhitung; BUKAN data kode-broker (itu premium)."""
import numpy as np, pandas as pd

def mfi(h,l,c,v,n=14):
    tp=(h+l+c)/3.0; rmf=tp*v; d=np.diff(tp,prepend=tp[0])
    pos=np.where(d>0,rmf,0.0); neg=np.where(d<0,rmf,0.0)
    ps=pd.Series(pos).rolling(n).sum().to_numpy(); ns=pd.Series(neg).rolling(n).sum().to_numpy()
    mr=ps/np.where(ns==0,np.nan,ns)
    return 100.0-100.0/(1.0+mr)

def cmf(h,l,c,v,n=20):
    rng=h-l; mfm=np.where(rng>0,((c-l)-(h-c))/np.where(rng>0,rng,1),0.0); mfv=mfm*v
    vs=pd.Series(v).rolling(n).sum().to_numpy()
    return pd.Series(mfv).rolling(n).sum().to_numpy()/np.where(vs==0,np.nan,vs)

def buysell_pct(c,v,n=20):
    """% volume di hari NAIK (proxy tekanan beli) selama n hari. >55 akumulasi, <45 distribusi."""
    up=np.diff(c,prepend=c[0])>=0
    bv=pd.Series(np.where(up,v,0.0)).rolling(n).sum().to_numpy()
    sv=pd.Series(np.where(~up,v,0.0)).rolling(n).sum().to_numpy()
    tot=bv+sv
    return np.where(tot>0, bv/np.where(tot>0,tot,1)*100.0, 50.0)

def obv_trend(c,v,n=20):
    d=np.sign(np.diff(c,prepend=c[0])); o=np.cumsum(d*v)
    return o, ((o[-1]-o[-1-n])/ (abs(o[-1-n])+1e-9) *100.0) if len(o)>n else 0.0

def _clean(x, nd=1):
    """NaN/inf -> None (JSON-safe), selain itu round."""
    try:
        x=float(x)
        if x!=x or x in (float('inf'),float('-inf')): return None
        return round(x, nd)
    except Exception: return None

def smart_money(df, look=20, big=2.0):
    """INFERENSI SM-vs-retail dari pola price+volume (BUKAN broksum kode-broker asli).
    Deteksi hari volume-besar (akumulasi/distribusi), close-location, divergence OBV, fase."""
    o=df['open'].to_numpy(float); h=df['high'].to_numpy(float); l=df['low'].to_numpy(float)
    c=df['close'].to_numpy(float); v=df['volume'].to_numpy(float)
    if len(c)<60: return {}
    vma=pd.Series(v).rolling(20).mean().to_numpy(); pc=np.roll(c,1); pc[0]=c[0]
    s=slice(-look,None)
    vv=v[s]; cc=c[s]; pcc=pc[s]; hh=h[s]; ll=l[s]; vm=vma[s]
    bigm=vv>=big*np.where(vm>0,vm,np.inf); up=cc>=pcc
    big_acc=int(np.sum(bigm&up)); big_dist=int(np.sum(bigm&~up))
    rng=hh-ll; clv=np.where(rng>0,((cc-ll)-(hh-cc))/np.where(rng>0,rng,1),0.0)
    clv_w=float(np.sum(clv*vv)/(np.sum(vv)+1e-9))                       # -1..+1, + = nutup dekat high (akumulasi)
    d=np.sign(np.diff(c,prepend=c[0])); obv=np.cumsum(d*v)
    obv_tr=float((obv[-1]-obv[-look])/(abs(obv[-look])+1e-9)*100)
    price_tr=float(c[-1]/c[-look]-1)*100
    if price_tr<-1 and obv_tr>2: diverg="divergence BULLISH (OBV naik saat harga turun = akumulasi diam-diam)"
    elif price_tr>1 and obv_tr<-2: diverg="divergence BEARISH (OBV turun saat harga naik = distribusi diam-diam)"
    else: diverg="selaras (volume sejalan harga)"
    if big_acc>big_dist and clv_w>0.08 and obv_tr>=0: who="SM AKUMULASI"
    elif big_dist>big_acc and (clv_w<-0.08 or obv_tr<0): who="SM DISTRIBUSI"
    elif (big_acc+big_dist)<=1 and abs(obv_tr)<2: who="RETAIL/sepi (minim volume besar)"
    else: who="campur/netral"
    return dict(sm=who, big_acc=big_acc, big_dist=big_dist, clv=_clean(clv_w,2),
                obv_tr=_clean(obv_tr,1), price_tr=_clean(price_tr,1), diverg=diverg)

def snapshot(df, n_mfi=14, n_cmf=20, n_bs=20):
    """Ringkas money-flow + inferensi SM/retail di bar terakhir. JSON-safe (NaN->None)."""
    h=df['high'].to_numpy(float); l=df['low'].to_numpy(float)
    c=df['close'].to_numpy(float); v=df['volume'].to_numpy(float)
    if len(c)<max(n_mfi,n_cmf,n_bs)+5: return {}
    m=mfi(h,l,c,v,n_mfi); cf=cmf(h,l,c,v,n_cmf); bs=buysell_pct(c,v,n_bs)
    _,obvt=obv_trend(c,v,20)
    bsv=_clean(bs[-1],1); bsv=50.0 if bsv is None else bsv
    lab="akumulasi" if bsv>=55 else ("distribusi" if bsv<=45 else "netral")
    out=dict(mfi=_clean(m[-1],1), cmf=_clean(cf[-1],3),
             buy_pct=bsv, sell_pct=round(100-bsv,1),
             obv_trend=_clean(obvt,1), flow=lab)
    out.update(smart_money(df))   # SM vs retail inferensi
    return out
