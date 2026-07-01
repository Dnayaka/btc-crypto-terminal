#!/usr/bin/env python3
"""fetch_lowcap.py — unduh universe LOW-CAP / small-cap IDX (kandidat ARA) via proxy.
Tulis ke data_lowcap/. Resumable. Setelah selesai, ringkas: harga terakhir, bar, base-rate ARA.

ARA tier (post-2021 simetris, approx): harga<200 -> 35%, 200-5000 -> 25%, >5000 -> 20%.
'ARA event' (proxy) = close naik >= ~tier-limit dari close kemarin (hari yg nutup mentok atas)."""
import os, sys, time, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_stocks import fetch_daily

HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,"data_lowcap")
os.makedirs(OUT, exist_ok=True)

# Curated ~100 small/mid-cap & spekulatif IDX (banyak yg sering ARA). Yang gagal di-skip.
TICK = """AGRO BBYB AMAR BBHI BGTG BBSI NOBU BVIC BABP DNAR BEKS BNBA BANK
BELI WIRG DCII EDGE MTDL DMMX HDIT NFCX ENVY KIOS LUCK CASH AXIO UVCR
RMKE CUAN PTMP RAJA RGAS PSSI MBSS HILL ENRG BIPI SGER ITMA MCOL GEMS
BRMS ZINC DKFT NICL NICE CITA PSAB SMMT IFSH
HRTA CARE FOOD CLEO COCO GOOD CAMP KEJU BEER FORE AYAM CMRY
POLL RDTX NZIA KIJA ASRI MTLA RISE NASA URBN ATAP DMAS
HEAL SILO SAME PRDA BMHS OMED HALO PRAY MTMH
OASA DOOH MORA TGUK CRSN NAYZ IRSX KOCI GTRA HOMI ASLC PEVE GULA SMIL MAXI ISEA FUTR VISI ARKO BLES PACK MENN LMAX MEDS PGUN VTNY MUTU WINE WIDI WGSH CBDK NETV SOLA PTMP""".split()

def ara_tier(price):
    return 0.35 if price<200 else (0.25 if price<5000 else 0.20)

def summarize():
    rows=[]
    for f in sorted(os.listdir(OUT)):
        if not f.endswith(".csv"): continue
        try: d=pd.read_csv(os.path.join(OUT,f),parse_dates=['dt'])
        except: continue
        if len(d)<200: continue
        c=d['close'].to_numpy(); pc=np.roll(c,1); pc[0]=c[0]
        ret=c/pc-1.0
        lim=np.array([ara_tier(p) for p in pc])
        ara=(ret>=lim*0.985)   # nutup mentok atas (proxy ARA)
        rows.append((f[:-4], len(d), c[-1], int(ara.sum()), round(ara.mean()*1000,2)))
    rows.sort(key=lambda x:-x[3])
    print(f"\n{'sym':10s} {'bar':>5} {'last':>8} {'#ARA':>5} {'ARA/1000hr':>10}")
    for sym,n,last,na,rate in rows:
        print(f"{sym:10s} {n:>5} {last:>8.0f} {na:>5} {rate:>10}")
    print(f"\nTOTAL {len(rows)} saham dgn data cukup. Total event ARA-proxy: {sum(r[3] for r in rows)}")
    json.dump({r[0]:dict(bars=r[1],last=r[2],ara=r[3]) for r in rows},
              open(os.path.join(OUT,"_lowcap_manifest.json"),"w"),indent=1)

if __name__=="__main__":
    if "--summary" in sys.argv: summarize(); sys.exit()
    syms=list(dict.fromkeys(TICK)); ok=0; t0=time.time()
    print(f"fetch {len(syms)} low-cap tickers -> {OUT}")
    for i,t in enumerate(syms,1):
        sym=t if t.endswith(".JK") else t+".JK"; p=os.path.join(OUT,sym+".csv")
        if os.path.exists(p):
            print(f"[{i}/{len(syms)}] {sym} cached"); ok+=1; continue
        df,info=fetch_daily(sym)
        if df is not None and len(df)>100:
            df.to_csv(p,index=False); ok+=1
            print(f"[{i}/{len(syms)}] {sym} OK {len(df)} bar last={df['close'].iloc[-1]:.0f} via {info}",flush=True)
        else:
            print(f"[{i}/{len(syms)}] {sym} {info}",flush=True)
        time.sleep(1.2)
    print(f"\nSELESAI {ok}/{len(syms)} dalam {time.time()-t0:.0f}s")
    summarize()
