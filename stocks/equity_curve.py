#!/usr/bin/env python3
"""equity_curve.py — kurva equity formula mean-reversion v1 dari modal Rp20jt, 3 level risiko
+ benchmark IHSG. Output PNG (tema terminal amber/hitam) + tabel progres tahunan."""
import os,heapq
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pf

MODAL=20_000_000
FINAL=dict(pf.CAND); FINAL.update(rsi_len=4, rsi_buy=15.0, rsi2_or=0.0,
            req_sma50_rising=True, sma50_rise_win=5, min_volval=1e10)
T=pf.all_trades(pf.load_data(), FINAL)
START=pd.Timestamp("2020-01-01"); END=pd.Timestamp("2026-06-30")
didx=pd.date_range(START,END,freq="D")

def curve(T,K,lev):
    Ts=T.sort_values('ed'); cash=1.0;inv=0.0;op=[];pts=[(START,1.0)]
    for _,r in Ts.iterrows():
        ed=pd.Timestamp(r['ed'])
        while op and op[0][0]<=ed:
            xd,a,pn=heapq.heappop(op);cash+=a*(1+lev*pn);inv-=a;pts.append((xd,cash+inv))
        if len(op)>=K or cash<=1e-9: continue
        tot=cash+inv;a=min(tot/K,cash);cash-=a;inv+=a;heapq.heappush(op,(pd.Timestamp(r['xd']),a,r['net']))
    while op: xd,a,pn=heapq.heappop(op);cash+=a*(1+lev*pn);inv-=a;pts.append((xd,cash+inv))
    s=pd.Series({d:e for d,e in pts}).sort_index()
    s=s[~s.index.duplicated(keep='last')].reindex(didx,method='ffill').fillna(1.0)
    return s*MODAL

# benchmark IHSG buy&hold dari 20jt
ix=pf.index_df(); ix=ix[(ix['dt']>=START)]; c=ix.set_index('dt')['close']
bench=(c/c.iloc[0]).reindex(didx,method='ffill').fillna(1.0)*MODAL

SETS=[("Konservatif K5·1x",5,1.0,"#27d07a"),
      ("Seimbang  K4·1x",4,1.0,"#ff8c1a"),
      ("Agresif   K3·1.5x",3,1.5,"#ff453a")]
curves={lbl:curve(T,K,lev) for lbl,K,lev,_ in SETS}

# ---- plot ----
plt.rcParams.update({"font.family":"monospace","font.size":10})
fig,ax=plt.subplots(figsize=(12,6.5),facecolor="#000000")
ax.set_facecolor("#070707")
for lbl,K,lev,col in SETS:
    s=curves[lbl]; ax.plot(s.index,s.values,color=col,lw=1.8,label=f"{lbl}  -> Rp{s.iloc[-1]/1e6:.0f}jt")
ax.plot(bench.index,bench.values,color="#8a7f63",lw=1.2,ls="--",label=f"IHSG buy&hold  -> Rp{bench.iloc[-1]/1e6:.0f}jt")
ax.axhline(MODAL,color="#3a3526",lw=1,ls=":")
ax.set_yscale("log")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v,_:f"{v/1e6:.0f}jt"))
ax.set_title("IDX Mean-Reversion v1  ·  Equity Curve dari Rp20jt  (2020-2026)",color="#ffb454",fontsize=13,pad=12)
ax.grid(True,color="#1b1810",lw=.6); ax.tick_params(colors="#8a7f63")
for sp in ax.spines.values(): sp.set_color("#1b1810")
leg=ax.legend(loc="upper left",facecolor="#070707",edgecolor="#1b1810",labelcolor="#e8e2d0",fontsize=9)
ax.set_xlabel("",color="#8a7f63")
OUT=os.path.join(os.path.dirname(__file__),"equity_curve.png")
plt.tight_layout(); plt.savefig(OUT,dpi=130,facecolor="#000000"); print("PNG ->",OUT)

# ---- tabel progres tahunan + stats ----
def maxdd(s): pk=np.maximum.accumulate(s.values); return ((pk-s.values)/pk).max()*100
print("\n== AKHIR TAHUN (saldo akun, Rp juta) ==")
yrs=[2020,2021,2022,2023,2024,2025,2026]
hdr="  tahun |"+"".join(f"{lbl.split()[0]:>13}" for lbl,_,_,_ in SETS)+f"{'IHSG':>11}"
print(hdr)
for y in yrs:
    eoy=pd.Timestamp(f"{y}-12-31") if y<2026 else END
    row=f"  {y}  |"
    for lbl,_,_,_ in SETS: row+=f"{curves[lbl].asof(eoy)/1e6:>13.0f}"
    row+=f"{bench.asof(eoy)/1e6:>11.0f}"
    print(row)
print("\n== RINGKAS ==")
for lbl,K,lev,_ in SETS:
    s=curves[lbl]; tot=(s.iloc[-1]/MODAL-1)*100; cagr=((s.iloc[-1]/MODAL)**(1/6.4)-1)*100
    print(f"  {lbl}: Rp20jt -> Rp{s.iloc[-1]/1e6:.1f}jt  (+{tot:.0f}%, CAGR {cagr:.1f}%/th, maxDD {maxdd(s):.0f}%)")
b=bench; print(f"  IHSG buy&hold      : Rp20jt -> Rp{b.iloc[-1]/1e6:.1f}jt  ({(b.iloc[-1]/MODAL-1)*100:+.0f}%, maxDD {maxdd(b):.0f}%)")
