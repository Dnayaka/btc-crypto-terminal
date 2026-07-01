#!/usr/bin/env python3
"""btc15m.py — maintain btc_15m_full.csv (INCREMENTAL gap-fetch: cuma tarik bar baru dari cache-terakhir
ke sekarang, ga boros) + jalankan v20 engine (RSI-momentum+pullback+regime-TP, tervalidasi) ->
btc_v20.json = {bars(history panjang), markers(LONG/SHORT entry+exit), stats}. Buat chart mirip TV.

  python3 btc15m.py            # update csv (gap) + tulis btc_v20.json
  python3 btc15m.py --nofetch  # skip update, cuma regen json dari csv
"""
import os, sys, json, time
import pandas as pd, numpy as np
import bot_v20_funding as B
from eng import run as eng_run, rsi, ema, atr, DEF
HERE=os.path.dirname(os.path.abspath(__file__)); CSV=os.path.join(HERE,"btc_15m_full.csv")
OUT=os.path.join(HERE,"btc_v20.json"); BAR_MS=15*60*1000; NBARS=48000   # ~500 hari (sejajar depth 1d 500-bar), 15m ga lagi cuma 1 bulan

def update_csv():
    df=pd.read_csv(CSV)
    last_ot=int(df["open_time"].iloc[-1])
    now=int(time.time()*1000)   # jam lokal (UTC epoch ms) — cukup buat batas bar-tertutup; hilangkan flap 'time gagal'
    start=last_ot+BAR_MS; rows=[]; loops=0
    while start<now and loops<50:
        try: kl=B.bget(f"/fapi/v1/klines?symbol=BTCUSDT&interval=15m&startTime={start}&limit=1500")
        except Exception as e: print("  klines gagal:",str(e)[:50]); break
        if not kl: break
        kl=[k for k in kl if k[6]<=now]   # bar tertutup saja
        if not kl: break
        rows+=kl; start=kl[-1][0]+BAR_MS; loops+=1
        if len(kl)<1500: break
    if not rows: print("  csv sudah terbaru"); return df
    nd=pd.DataFrame(rows,columns=["open_time","open","high","low","close","volume","close_time","qav","trades","tbbav","tbqav","ig"])
    nd=nd[["open_time","open","high","low","close","volume","qav","trades","tbbav"]]
    for c in ["open","high","low","close","volume"]: nd[c]=nd[c].astype(float)
    nd["dt"]=pd.to_datetime(nd["open_time"],unit="ms",utc=True)
    df=pd.concat([df,nd]).drop_duplicates(subset=["open_time"],keep="last").sort_values("open_time").reset_index(drop=True)
    df.to_csv(CSV,index=False)
    print(f"  +{len(rows)} bar baru -> {df['dt'].iloc[-1] if 'dt' in df else df['open_time'].iloc[-1]}")
    return df

def v20_trades(df):
    o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float);c=df['close'].to_numpy(float)
    ctx=B.build_v20_context(df)
    R=rsi(c,DEF['rsi_len']);E=ema(c,DEF['ema_len']);A=atr(h,l,c,DEF['atr_len']);ap=A/c*100;rng=h-l
    body=np.where(rng>0,np.abs(c-o)/np.where(rng>0,rng,1),0.0)
    aL=B.pbsig(o,h,l,c,R,E,ap,body,'long'); aS=B.pbsig(o,h,l,c,R,E,ap,body,'short')
    res,t=eng_run(df,{'add_long':aL,'add_short':aS,'tp':ctx['tp'],'sl':ctx['sl']})
    return res,t

def build():
    df=pd.read_csv(CSV) if "--nofetch" in sys.argv else update_csv()
    if "dt" not in df: df["dt"]=pd.to_datetime(df["open_time"],unit="ms",utc=True)
    res,t=v20_trades(df)
    n=len(df); w0=max(0,n-NBARS); wt=w0    # marker/trade window = bars window (konsisten, ga numpuk di pojok kiri)
    ot=df["open_time"].to_numpy()
    bars=[{"time":int(ot[i]//1000),"open":float(df['open'].iloc[i]),"high":float(df['high'].iloc[i]),
           "low":float(df['low'].iloc[i]),"close":float(df['close'].iloc[i]),"volume":float(df['volume'].iloc[i])} for i in range(w0,n)]
    ctx=B.build_v20_context(df); tparr=ctx['tp']; slarr=ctx['sl']
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
    mk.sort(key=lambda x:x["time"])   # lightweight-charts wajib ascending
    # === posisi OPEN (belum TP/SL) -- eng.run cuma nulis trade pas CLOSE, jadi posisi live nyangkut
    # tanpa box sampe exit. Fix: tempel synthetic "open trade" dari state bot biar box langsung muncul. ===
    try:
        st=json.load(open(os.path.join(HERE,"bot_v22_state.json"))).get("v20",{})
        pos=int(st.get("pos",0))
        if pos!=0 and st.get("entry"):
            et_open=int(ot[max(0,int(st.get("entry_i",n-1)))]//1000)
            trades.append({"et":et_open,"xt":int(ot[-1]//1000),"dir":pos,
                            "entry":round(float(st["entry"]),1),"tp":round(float(st.get("tp",0)),1),
                            "sl":round(float(st.get("sl",0)),1),"ret":None,"win":None,"reason":"open"})
    except Exception: pass
    # === equity curve PENUH (semua trade) buat halaman performa /performa ===
    eqc=[]; eq=1.0; pk=1.0; mdd=0.0
    for _,r in t.sort_values('exit_bar').iterrows():
        eq*=(1.0+float(r['net'])); xb=int(r['exit_bar'])
        xt=int(ot[xb]//1000) if xb<len(ot) else int(ot[-1]//1000)
        pk=max(pk,eq); mdd=max(mdd,(pk-eq)/pk if pk>0 else 0.0)
        eqc.append([xt, round(eq,5)])
    perf={"ret":round((eq-1)*100,1),"maxdd":round(mdd*100,1),"n":int(len(t)),"wr":res['wr'],
          "start":eqc[0][0] if eqc else 0,"end":eqc[-1][0] if eqc else 0,"cal":round((eq-1)/mdd,1) if mdd>0 else 0}
    out={"_ts":int(time.time()),"bars":bars,"markers":mk,"trades":trades,
         "stats":{"n":int(res['n']),"wr":res['wr'],"ret":res['ret'],"nl":res.get('nl'),"ns":res.get('ns')},
         "equity":eqc,"perf":perf,
         "last":df['open_time'].iloc[-1]/1000}
    json.dump(out,open(OUT,"w"))
    print(f"btc_v20.json: {len(bars)} bar, {len(mk)} marker, {res['n']} trade WR{res['wr']} -> {OUT}")

if __name__=="__main__": build()
