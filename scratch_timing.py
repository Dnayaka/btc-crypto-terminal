#!/usr/bin/env python3
"""Timing test (errors_v20.json): apakah blok jam/hari buruk atau config-per-hari PROFIT & TAHAN OOS.
errors bilang buruk = Sel/Rab/Kam + NY 13-16 UTC + jam 11/14. Uji rigor: full + per-year + OOS +
PERSISTENSI (jam/hari buruk di TRAIN masih buruk di TEST? kalau ga -> overfit)."""
import numpy as np, pandas as pd
from eng import rsi, ema, atr, signals, DEF, run as eng_run
from bot_v20_funding import pbsig, TP_BASE, TP_GENTLE, TP_WALL, SL_V20

HERE="/home/dnayaka/Documents/dynamic_rsi/btc-terminal"
df=pd.read_csv(HERE+"/btc_15m_full.csv",parse_dates=['dt'])
o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float);c=df['close'].to_numpy(float)
n=len(c)
R=rsi(c,DEF['rsi_len']);E=ema(c,DEF['ema_len']);A=atr(h,l,c,DEF['atr_len'])
ap=A/c*100.0; rng=h-l; body=np.where(rng>0,np.abs(c-o)/np.where(rng>0,rng,1),0.0)
aL=pbsig(o,h,l,c,R,E,ap,body,'long'); aS=pbsig(o,h,l,c,R,E,ap,body,'short')
TPa=np.full(n,TP_BASE); TPa[ap>TP_WALL]=TP_GENTLE; SLa=np.full(n,SL_V20)
hour=df['dt'].dt.hour.to_numpy(); dow=df['dt'].dt.dayofweek.to_numpy(); year=df['dt'].dt.year.to_numpy()

def base_kw(): return {'add_long':aL,'add_short':aS,'tp':TPa,'sl':SLa}
def peryear(t):
    if len(t)==0: return {}
    yy=year[t['exit_bar'].to_numpy()]; g=pd.DataFrame({'y':yy,'net':t['net'].to_numpy()})
    return {int(y):round((np.prod(1+gg['net'])-1)*100,1) for y,gg in g.groupby('y')}

def run_block(block):
    kw=base_kw(); kw['extra_long']=~block; kw['extra_short']=~block
    return eng_run(df,kw)

r0,t0=eng_run(df,base_kw())
print(f"BASE: ret{r0['ret']:+.0f} dd{r0['dd']} wr{r0['wr']} n{r0['n']} cal{r0['calmar']}")

# ---- PERSISTENSI: WR per jam & hari, TRAIN(70) vs TEST(30) ----
cut=int(n*0.70)
def wr_by(keyarr, t, lo, hi):
    tt=t[(t['exit_bar']>=lo)&(t['exit_bar']<hi)].copy()
    tt['k']=keyarr[tt['entry_bar'].to_numpy()]; out={}
    for k,g in tt.groupby('k'): out[int(k)]=(round((g['net']>0).mean()*100,1),len(g))
    return out
print("\n=== PERSISTENSI hari (WR train vs test) — kalau ranking beda = overfit ===")
wtr=wr_by(dow,t0,0,cut); wte=wr_by(dow,t0,cut,n)
nm=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
print(f"{'day':>4} {'train WR(n)':>14} {'test WR(n)':>14}")
for dd in range(7):
    a=wtr.get(dd,('-','-')); b=wte.get(dd,('-','-'))
    print(f"{nm[dd]:>4} {str(a):>14} {str(b):>14}")

print("\n=== A) Blok HARI buruk (Sel/Rab/Kam) ===")
for label,days in [('block Tue',[1]),('block Tue+Wed',[1,2]),('block Tue+Wed+Thu',[1,2,3]),('block Wed only',[2])]:
    blk=np.isin(dow,days); r,t=run_block(blk); py=peryear(t)
    print(f"  {label:>20}: ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['calmar']} allpos={all(v>0 for v in py.values())}")

print("\n=== B) Blok JAM buruk (NY & burukan) ===")
for label,hrs in [('block NY 13-16',[13,14,15,16]),('block 14 only',[14]),('block 11,14',[11,14]),
                   ('block 11-16',[11,12,13,14,15,16]),('block 14,15',[14,15])]:
    blk=np.isin(hour,hrs); r,t=run_block(blk); py=peryear(t)
    print(f"  {label:>20}: ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['calmar']} allpos={all(v>0 for v in py.values())}")

print("\n=== C) OOS: identifikasi buruk di TRAIN, terapkan ke TEST (jujur) ===")
# hari/jam dgn EV<0 atau WR<58 di TRAIN
def ev_by(keyarr,t,lo,hi):
    tt=t[(t['exit_bar']>=lo)&(t['exit_bar']<hi)].copy(); tt['k']=keyarr[tt['entry_bar'].to_numpy()]
    return {int(k):g['net'].mean() for k,g in tt.groupby('k')}
evd=ev_by(dow,t0,0,cut); baddays=[k for k,v in evd.items() if v<0.001]
evh=ev_by(hour,t0,0,cut); badhrs=[k for k,v in evh.items() if v<0.0]
print(f"  TRAIN bad days(EV<0.1%): {[nm[d] for d in baddays]}  bad hours(EV<0): {sorted(badhrs)}")
for label,blk in [('block train-bad-days',np.isin(dow,baddays)),('block train-bad-hours',np.isin(hour,badhrs)),
                  ('block both',np.isin(dow,baddays)|np.isin(hour,badhrs))]:
    _,t=run_block(blk)
    tr=t[t['exit_bar']<cut]; te=t[t['exit_bar']>=cut]
    def m(x):
        if len(x)==0: return (0,0,0)
        eq=np.cumprod(1+x['net'].to_numpy());dd=((np.maximum.accumulate(eq)-eq)/np.maximum.accumulate(eq)).max()*100
        ret=(eq[-1]-1)*100;return (round(ret),round(dd,1),round(ret/dd,1) if dd>0 else 0)
    # baseline slices
    bt=m(t0[t0['exit_bar']<cut]); be=m(t0[t0['exit_bar']>=cut]); ft=m(tr); fe=m(te)
    print(f"  {label:>22}: TEST base ret{be[0]}/cal{be[2]} -> filtered ret{fe[0]}/cal{fe[2]}")
