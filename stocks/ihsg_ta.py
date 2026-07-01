#!/usr/bin/env python3
"""ihsg_ta.py — ANALISA TEKNIKAL PENUH IHSG (^JKSE). Tren (SMA20/50/200, cross), momentum
(RSI, MACD, Stochastic), volatilitas (ATR, Bollinger), level (S/R, 52w, swing), volume, regime,
+ skor bias komposit (bullish/netral/bearish) dengan alasan. Output: ringkasan teks + ihsg_ta.json.

  python3 ihsg_ta.py            # fetch live ^JKSE, cetak + tulis ihsg_ta.json
  python3 ihsg_ta.py --cached   # pakai data_lowcap/.. (offline, _JKSE.csv di data/)
"""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seng
HERE=os.path.dirname(os.path.abspath(__file__))

def macd(c, f=12, s=26, sig=9):
    ef=seng.ema(c,f); es=seng.ema(c,s); line=ef-es
    sigl=seng.ema(line[~np.isnan(line)], sig)
    out=np.full(len(c),np.nan); out[len(c)-len(sigl):]=sigl
    return line, out, line-out
def stoch(h,l,c,n=14,d=3):
    ll=pd.Series(l).rolling(n).min().to_numpy(); hh=pd.Series(h).rolling(n).max().to_numpy()
    k=100*(c-ll)/np.where(hh-ll>0,hh-ll,np.nan); dd=pd.Series(k).rolling(d).mean().to_numpy()
    return k, dd

def analyze(df):
    o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float)
    c=df['close'].to_numpy(float);v=df['volume'].to_numpy(float); n=len(c)
    px=c[-1]; prev=c[-2]; chg=(px/prev-1)*100
    s20=seng.sma(c,20);s50=seng.sma(c,50);s200=seng.sma(c,200)
    r=seng.rsi(c,14); a=seng.atr(h,l,c,14); atrp=a[-1]/px*100
    ml,msig,mhist=macd(c); k,dstoch=stoch(h,l,c)
    bm=seng.sma(c,20); bsd=pd.Series(c).rolling(20).std(ddof=0).to_numpy()
    bu=bm+2*bsd; bl=bm-2*bsd; bpos=(px-bl[-1])/(bu[-1]-bl[-1])*100 if bu[-1]>bl[-1] else 50
    hi52=h[-252:].max(); lo52=l[-252:].min()
    sw_hi=h[-60:].max(); sw_lo=l[-60:].min()
    volma=seng.sma(v,20)
    def sl(arr,k=5): return (arr[-1]-arr[-1-k])/arr[-1-k]*100  # slope % k-bar
    # ---- regime ----
    align_up = px>s20[-1]>s50[-1]>s200[-1]; align_dn = px<s20[-1]<s50[-1]<s200[-1]
    s200_up = sl(s200,20)>0
    if align_up and s200_up: regime="STRONG UPTREND"
    elif px>s200[-1] and s50[-1]>s200[-1]: regime="UPTREND"
    elif align_dn: regime="STRONG DOWNTREND"
    elif px<s200[-1] and s50[-1]<s200[-1]: regime="DOWNTREND"
    else: regime="RANGE / TRANSISI"
    golden = s50[-1]>s200[-1] and s50[-2]<=s200[-2]; death=s50[-1]<s200[-1] and s50[-2]>=s200[-2]
    # ---- skor bias (−100..+100) ----
    sc=0; reasons=[]
    if px>s200[-1]: sc+=20; reasons.append(f"di ATAS SMA200 ({(px/s200[-1]-1)*100:+.1f}%) = struktur bullish")
    else: sc-=20; reasons.append(f"di BAWAH SMA200 ({(px/s200[-1]-1)*100:+.1f}%) = struktur bearish")
    if px>s50[-1]: sc+=10
    else: sc-=10
    if s50[-1]>s200[-1]: sc+=10; reasons.append("SMA50>SMA200 (tren menengah naik)")
    else: sc-=10; reasons.append("SMA50<SMA200 (tren menengah turun)")
    if sl(s50,10)>0: sc+=8
    else: sc-=8
    rr=r[-1]
    if rr>70: sc-=8; reasons.append(f"RSI {rr:.0f} = overbought (waspada koreksi)")
    elif rr<30: sc+=8; reasons.append(f"RSI {rr:.0f} = oversold (potensi pantul)")
    elif rr>=50: sc+=8; reasons.append(f"RSI {rr:.0f} = momentum positif")
    else: sc-=5; reasons.append(f"RSI {rr:.0f} = momentum lemah")
    if mhist[-1]>0 and mhist[-1]>mhist[-2]: sc+=10; reasons.append("MACD histogram positif & menguat")
    elif mhist[-1]>0: sc+=5
    elif mhist[-1]<0 and mhist[-1]<mhist[-2]: sc-=10; reasons.append("MACD histogram negatif & melemah")
    else: sc-=5
    if k[-1]>80: sc-=5
    elif k[-1]<20: sc+=5
    if golden: sc+=15; reasons.append("⭐ GOLDEN CROSS baru (SMA50 tembus atas SMA200)")
    if death: sc-=15; reasons.append("⚠️ DEATH CROSS baru (SMA50 tembus bawah SMA200)")
    bias = "BULLISH" if sc>=20 else ("BEARISH" if sc<=-20 else "NETRAL")
    out=dict(
        date=str(pd.Timestamp(df['dt'].iloc[-1]).date()), price=round(px,1), change_pct=round(chg,2),
        regime=regime, bias=bias, score=int(np.clip(sc,-100,100)),
        sma20=round(s20[-1],1), sma50=round(s50[-1],1), sma200=round(s200[-1],1),
        dist_sma200_pct=round((px/s200[-1]-1)*100,2),
        rsi=round(r[-1],1), macd_hist=round(mhist[-1],2), stoch_k=round(k[-1],1),
        atr_pct=round(atrp,2), bb_pos_pct=round(bpos,1),
        hi52=round(hi52,1), lo52=round(lo52,1), dist_hi52_pct=round((px/hi52-1)*100,2),
        support=round(max(sw_lo, s50[-1] if s50[-1]<px else sw_lo),1),
        resistance=round(min(sw_hi if sw_hi>px else hi52, hi52),1),
        vol_vs_ma=round(v[-1]/volma[-1],2) if volma[-1]>0 else None,
        golden_cross=bool(golden), death_cross=bool(death),
        reasons=reasons,
    )
    return out

def main():
    if "--cached" in sys.argv:
        df=pd.read_csv(os.path.join(HERE,"data","_JKSE.csv"),parse_dates=['dt'])
    else:
        from fetch_stocks import fetch_daily
        df,info=fetch_daily("^JKSE")
        if df is None:
            print("fetch gagal, fallback cached"); df=pd.read_csv(os.path.join(HERE,"data","_JKSE.csv"),parse_dates=['dt'])
    a=analyze(df)
    import math as _m
    a={k:(None if isinstance(v,float) and (_m.isnan(v) or _m.isinf(v)) else v) for k,v in a.items()}   # C6: JSON-safe (NaN/inf -> null) biar frontend JSON.parse ga error
    _tmp=os.path.join(HERE,"ihsg_ta.json")+".tmp"
    with open(_tmp,"w") as _f: json.dump(a,_f,indent=1)
    os.replace(_tmp, os.path.join(HERE,"ihsg_ta.json"))
    arrow="▲" if a['change_pct']>=0 else "▼"
    print(f"\n=== IHSG · {a['date']} ===")
    print(f"  Harga {a['price']:,.0f}  {arrow}{a['change_pct']:+.2f}%   |  REGIME: {a['regime']}   BIAS: {a['bias']} (skor {a['score']:+d})")
    print(f"  SMA20 {a['sma20']:,.0f} · SMA50 {a['sma50']:,.0f} · SMA200 {a['sma200']:,.0f} (jarak {a['dist_sma200_pct']:+.1f}%)")
    print(f"  RSI {a['rsi']} · MACDhist {a['macd_hist']} · Stoch {a['stoch_k']} · ATR {a['atr_pct']}% · BB-pos {a['bb_pos_pct']}%")
    print(f"  52w: {a['lo52']:,.0f} – {a['hi52']:,.0f} (dari high {a['dist_hi52_pct']:+.1f}%) · S {a['support']:,.0f} / R {a['resistance']:,.0f} · vol {a['vol_vs_ma']}x")
    print("  Alasan:");  [print(f"   • {x}") for x in a['reasons']]
    print(f"\n  -> ihsg_ta.json ditulis.")

if __name__=="__main__": main()
