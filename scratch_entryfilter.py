#!/usr/bin/env python3
"""FIX HULU: filter entry pakai skor logistik (fitur: volume, rejection-wick, extension, ATR, dst).
Latih koef di 70% trade awal -> skor per-sinyal -> buang skor terendah. Cek FULL+OOS+per-year+perturbasi.
Pertanyaan kunci: WR naik OOS (0.607 AUC) -> apa CALMAR juga naik? (buang trade bisa turunin ret)."""
import numpy as np, pandas as pd
from eng import rsi,ema,atr,signals,DEF,run as eng_run
from bot_v20_funding import pbsig,TP_BASE,TP_GENTLE,TP_WALL,SL_V20
df=pd.read_csv('btc_15m_full.csv',parse_dates=['dt'])
o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float);c=df['close'].to_numpy(float)
vol=df['volume'].to_numpy(float);n=len(c);year=df['dt'].dt.year.to_numpy()
R=rsi(c,DEF['rsi_len']);E=ema(c,DEF['ema_len']);A=atr(h,l,c,DEF['atr_len'])
ap=A/c*100;rng=np.maximum(h-l,1e-9);bodyr=np.abs(c-o)/rng
aL=pbsig(o,h,l,c,R,E,ap,bodyr,'long');aS=pbsig(o,h,l,c,R,E,ap,bodyr,'short')
TPa=np.full(n,TP_BASE);TPa[ap>TP_WALL]=TP_GENTLE;SLa=np.full(n,SL_V20)
volma=pd.Series(vol).rolling(20).mean().to_numpy(); volr=vol/np.where(volma>0,volma,np.nan)
hi20=pd.Series(h).rolling(20).max().shift(1).to_numpy(); lo20=pd.Series(l).rolling(20).min().shift(1).to_numpy()
uwick=(h-np.maximum(o,c))/rng; lwick=(np.minimum(o,c)-l)/rng
FEATS=['emadist','rsi_lvl','rgap1','rgap2','rej_wick','ext','ret5','volr','ap','body']
def feat_at(s,d):
    sgn=1 if d>0 else -1
    emadist=(c[s]-E[s])/E[s]*100*sgn
    rsi_lvl=(R[s]-82)*sgn if d>0 else (18-R[s])
    rgap1=(R[s]-R[s-1])*sgn; rgap2=(R[s]-R[s-2])*sgn
    rej=uwick[s] if d>0 else lwick[s]
    ext=((c[s]-hi20[s])/c[s]*100) if d>0 else ((lo20[s]-c[s])/c[s]*100)
    ret5=(c[s]/c[s-5]-1)*100*sgn
    return [emadist,rsi_lvl,rgap1,rgap2,rej,ext,ret5,volr[s],ap[s],bodyr[s]]

# --- kumpulkan fitur trade utk latih (di signal bar = entry_bar-1) ---
r0,t0=eng_run(df,{'add_long':aL,'add_short':aS,'tp':TPa,'sl':SLa})
X=[];Y=[];EB=[]
for _,tr in t0.iterrows():
    s=int(tr['entry_bar'])-1; d=int(tr['dir'])
    if s<25 or np.isnan(volr[s]) or np.isnan(hi20[s]): continue
    X.append(feat_at(s,d)); Y.append(int(tr['net']>0)); EB.append(int(tr['entry_bar']))
X=np.array(X,float);Y=np.array(Y,float);EB=np.array(EB)
cutt=int(len(X)*0.70)
mu=X[:cutt].mean(0);sd=X[:cutt].std(0)
def fit(Xs,y,l2=0.01,it=4000,lr=0.1):
    w=np.zeros(Xs.shape[1]);b=0.0
    for _ in range(it):
        p=1/(1+np.exp(-(Xs@w+b)));g=p-y; w-=lr*(Xs.T@g/len(y)+l2*w);b-=lr*g.mean()
    return w,b
w,b=fit((X[:cutt]-mu)/sd,Y[:cutt])

# --- skor per-bar utk semua sinyal, bangun mask filter ---
def score_bar(s,d):
    f=np.array(feat_at(s,d),float); z=((f-mu)/sd)@w+b; return 1/(1+np.exp(-z))
sig_bars=np.where(aL|aS| signals(df,{**DEF,'add_long':aL,'add_short':aS},(o,h,l,c,R,E,A))[0] |
                  signals(df,{**DEF,'add_long':aL,'add_short':aS},(o,h,l,c,R,E,A))[1])[0]
LS,SS,_,_=signals(df,{**DEF,'add_long':aL,'add_short':aS},(o,h,l,c,R,E,A))
scoreL=np.zeros(n);scoreS=np.zeros(n)
for s in range(25,n):
    if np.isnan(volr[s]) or np.isnan(hi20[s]): continue
    if LS[s]: scoreL[s]=score_bar(s,1)
    if SS[s]: scoreS[s]=score_bar(s,-1)

def peryear(t):
    if len(t)==0: return {}
    yy=year[t['exit_bar'].to_numpy()];g=pd.DataFrame({'y':yy,'net':t['net'].to_numpy()})
    return {int(y):round((np.prod(1+gg['net'])-1)*100,1) for y,gg in g.groupby('y')}
cutbar=int(n*0.70)
def run_thr(thr):
    okL=(scoreL>=thr)|(~LS); okS=(scoreS>=thr)|(~SS)
    kw={'add_long':aL,'add_short':aS,'tp':TPa,'sl':SLa,'extra_long':okL,'extra_short':okS}
    r,t=eng_run(df,kw)
    def m(x):
        if len(x)==0:return(0,0,0)
        eq=np.cumprod(1+x['net'].to_numpy());pk=np.maximum.accumulate(eq);dd=((pk-eq)/pk).max()*100
        rr=(eq[-1]-1)*100;return(round(rr),round(dd,1),round(rr/dd,1) if dd>0 else 0)
    return r,t,m(t[t.exit_bar<cutbar]),m(t[t.exit_bar>=cutbar])

# threshold dari kuantil skor TRAIN
strain=[]
for _,tr in t0.iloc[:cutt].iterrows():
    s=int(tr['entry_bar'])-1;d=int(tr['dir'])
    if s<25 or np.isnan(volr[s]) or np.isnan(hi20[s]):continue
    strain.append(score_bar(s,d))
strain=np.array(strain)
print(f'BASE ret{r0["ret"]:+.0f} dd{r0["dd"]} wr{r0["wr"]} n{r0["n"]} cal{r0["calmar"]}')
print(f"AUC-based filter. koef: {dict(zip(FEATS,w.round(2)))}")
print(f"{'drop%':>6}{'thr':>6} | {'ret':>7}{'dd':>6}{'wr':>6}{'n':>5}{'cal':>6} allpos | {'TRAINcal':>9}{'TESTcal':>8} (base T{22})")
for q in [0.0,0.10,0.15,0.20,0.25,0.30,0.40]:
    thr=np.quantile(strain,q) if q>0 else -1
    r,t,tr_,te_=run_thr(thr);py=peryear(t);apos=all(v>0 for v in py.values())
    print(f'{int(q*100):>5}%{thr:>6.2f} | {r["ret"]:>+7.0f}{r["dd"]:>6}{r["wr"]:>6}{r["n"]:>5}{r["calmar"]:>6} {str(apos):>5} | {tr_[2]:>9}{te_[2]:>8}')
