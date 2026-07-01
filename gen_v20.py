#!/usr/bin/env python3
"""gen_v20.py — generic v20 chart-json generator utk ETH/SOL (mirror btc15m.py, param per-ticker
via MULTI_PARAMS). BTC TETAP pakai btc15m.py (0 disentuh -- best-validated path).
  python3 gen_v20.py ETHUSDT   # update csv (gap) + tulis eth_v20.json
  python3 gen_v20.py SOLUSDT --nofetch
"""
import os, sys, json, time
import pandas as pd, numpy as np
import bot_v20_funding as B
from eng import run as eng_run, DEF

HERE=os.path.dirname(os.path.abspath(__file__))
SYM=sys.argv[1] if len(sys.argv)>1 else "ETHUSDT"
TAG=SYM[:3].lower()
CSV=os.path.join(HERE,f"{TAG}_15m_full.csv"); OUT=os.path.join(HERE,f"{TAG}_v20.json")
BAR_MS=15*60*1000; NBARS=48000

def update_csv():
    df=pd.read_csv(CSV)
    last_ot=int(df["open_time"].iloc[-1])
    now=int(time.time()*1000)
    start=last_ot+BAR_MS; rows=[]; loops=0
    while start<now and loops<50:
        try: kl=B.bget(f"/fapi/v1/klines?symbol={SYM}&interval=15m&startTime={start}&limit=1500")
        except Exception as e: print("  klines gagal:",str(e)[:50]); break
        if not kl: break
        kl=[k for k in kl if k[6]<=now]
        if not kl: break
        rows+=kl; start=kl[-1][0]+BAR_MS; loops+=1
        if len(kl)<1500: break
    if not rows: print("  csv sudah terbaru"); return df
    nd=pd.DataFrame(rows,columns=["open_time","open","high","low","close","volume","close_time","qav","trades","tbbav","tbqav","ig"])
    nd=nd[["open_time","open","high","low","close","volume"]]
    for c in ["open","high","low","close","volume"]: nd[c]=nd[c].astype(float)
    df=pd.concat([df,nd]).drop_duplicates(subset=["open_time"],keep="last").sort_values("open_time").reset_index(drop=True)
    df.to_csv(CSV,index=False)
    print(f"  +{len(rows)} bar baru")
    return df

def v20_trades(df):
    ctx=B.build_v20_context_multi(df, SYM)   # ctx['long']/['short'] = base OR pullback (predikat penuh v20)
    p=B.MULTI_PARAMS.get(SYM,B.MULTI_PARAMS['BTCUSDT'])
    cf=dict(DEF); cf['max_atr']=p['ceil']; cf['atr_floor']=p['floor']
    cf['add_long']=ctx['long']; cf['add_short']=ctx['short']   # OR-add (BUKAN extra_/AND -- jaga sinyal pullback, sama pola scratch_ext.py)
    cf['tp']=ctx['tp']; cf['sl']=ctx['sl']
    res,t=eng_run(df,cf)
    return res,t,ctx

def build():
    df=pd.read_csv(CSV) if "--nofetch" in sys.argv else update_csv()
    if "dt" not in df: df["dt"]=pd.to_datetime(df["open_time"],unit="ms",utc=True)
    res,t,ctx=v20_trades(df)
    n=len(df); w0=max(0,n-NBARS); wt=w0
    ot=df["open_time"].to_numpy()
    bars=[{"time":int(ot[i]//1000),"open":float(df['open'].iloc[i]),"high":float(df['high'].iloc[i]),
           "low":float(df['low'].iloc[i]),"close":float(df['close'].iloc[i]),"volume":float(df['volume'].iloc[i])} for i in range(w0,n)]
    tparr=ctx['tp']; slarr=ctx['sl']
    mk=[]; trades=[]
    for _,r in t.iterrows():
        eb=int(r['entry_bar']); xb=int(r['exit_bar']); d=int(r['dir'])
        if xb<wt: continue
        win=bool(r['net']>0); ret=round(float(r['net'])*100,2); ep=float(r['entry'])
        tpp=float(tparr[eb-1]); spp=float(slarr[eb-1])
        if d>0: tpl=ep*(1+tpp/100); sll=ep*(1-spp/100)
        else:   tpl=ep*(1-tpp/100); sll=ep*(1+spp/100)
        et=int(ot[eb]//1000); xt=int(ot[xb]//1000)
        trades.append({"et":et,"xt":xt,"dir":d,"entry":round(ep,1),"tp":round(tpl,1),"sl":round(sll,1),"ret":ret,"win":win,"reason":str(r['reason'])})
        if eb>=wt:
            if d>0: mk.append({"time":et,"position":"belowBar","color":"#27d07a","shape":"arrowUp","text":"LONG"})
            else:   mk.append({"time":et,"position":"aboveBar","color":"#ff453a","shape":"arrowDown","text":"SHORT"})
        col="#27d07a" if win else "#ff453a"
        pos="aboveBar" if d>0 else "belowBar"; shp="arrowDown" if d>0 else "arrowUp"
        mk.append({"time":xt,"position":pos,"color":col,"shape":shp,"text":("+" if ret>=0 else "")+str(ret)+"%"})
    mk.sort(key=lambda x:x["time"])
    eqc=[]; eq=1.0; pk=1.0; mdd=0.0
    for _,r in t.sort_values('exit_bar').iterrows():
        eq*=(1.0+float(r['net'])); xb=int(r['exit_bar'])
        xt=int(ot[xb]//1000) if xb<len(ot) else int(ot[-1]//1000)
        pk=max(pk,eq); mdd=max(mdd,(pk-eq)/pk if pk>0 else 0.0)
        eqc.append([xt, round(eq,5)])
    close_arr=df['close'].to_numpy(float)
    if eqc:
        eb0=int(t['exit_bar'].min()); c0=close_arr[max(0,eb0-1)] if eb0>0 else close_arr[0]
        step=max(1,(n-eb0)//400)
        hold=[[int(ot[i]//1000), round(float(close_arr[i]/c0),5)] for i in range(eb0,n,step)]
    else: hold=[]
    perf={"ret":round((eq-1)*100,1),"maxdd":round(mdd*100,1),"n":int(len(t)),"wr":res['wr'],
          "start":eqc[0][0] if eqc else 0,"end":eqc[-1][0] if eqc else 0,"cal":round((eq-1)/mdd,1) if mdd>0 else 0,
          "hold_ret":round((hold[-1][1]-1)*100,1) if hold else 0}
    out={"_ts":int(time.time()),"sym":SYM,"bars":bars,"markers":mk,"trades":trades,
         "stats":{"n":int(res['n']),"wr":res['wr'],"ret":res['ret'],"nl":res.get('nl'),"ns":res.get('ns')},
         "equity":eqc,"hold":hold,"perf":perf,"last":df['open_time'].iloc[-1]/1000}
    json.dump(out,open(OUT,"w"))
    print(f"{TAG}_v20.json: {len(bars)} bar, {len(mk)} marker, {res['n']} trade WR{res['wr']} -> {OUT}")

if __name__=="__main__": build()
