#!/usr/bin/env python3
"""Ide user: tiered partial-TP (jual bertahap naik) + PARTIAL RE-ENTRY pas harga balik ke ENTRY (re-arm siklus).
Semua lot di harga entry (re-entry di e0) -> PnL simpel. Anti look-ahead: re-entry != bar sama dgn tier-sell.
Banding vs BASE v20 + vs 4-tier polos. Validasi full + per-year + OOS."""
import numpy as np, pandas as pd
from eng import rsi,ema,atr,signals,DEF,run as eng_run
from bot_v20_funding import pbsig,TP_BASE,TP_GENTLE,TP_WALL,SL_V20
df=pd.read_csv('btc_15m_full.csv',parse_dates=['dt'])
o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float);c=df['close'].to_numpy(float)
n=len(c);year=df['dt'].dt.year.to_numpy()
R=rsi(c,DEF['rsi_len']);E=ema(c,DEF['ema_len']);A=atr(h,l,c,DEF['atr_len'])
ap=A/c*100;rng=np.maximum(h-l,1e-9);bodyr=np.abs(c-o)/rng
aL=pbsig(o,h,l,c,R,E,ap,bodyr,'long');aS=pbsig(o,h,l,c,R,E,ap,bodyr,'short')
TPa=np.full(n,TP_BASE);TPa[ap>TP_WALL]=TP_GENTLE;SLa=np.full(n,SL_V20)
LS,SS,_,_=signals(df,{**DEF,'add_long':aL,'add_short':aS},(o,h,l,c,R,E,A))

def run(tiers=(1.0,1.5,2.0,2.5), frac=0.25, sl=1.9, max_re=3, reentry=True, fee=0.0002):
    """tiers = level% jual frac tiap tier. re-entry: balik ke e0 -> beli-balik size hilang, re-arm tier.
    fee = 0.02% PER FILL (limit/maker): dicharge di entry + tiap tier-sell + tiap re-entry + exit."""
    cd=DEF['cooldown'];start=max(DEF['warmup'],DEF['ema_len']+2)
    pos=0;e0=0;eb=0;led=0;leb=-10**9;tr=[]
    size=0.0; sold=[]; reidx=0; last_act=-1; realized=0.0
    for i in range(start,n):
        if pos!=0:
            d=pos; slp=e0*(1-sl/100) if d>0 else e0*(1+sl/100)
            # 1) SL (sisa size)
            hit=(l[i]<=slp) if d>0 else (h[i]>=slp)
            if hit:
                px=min(o[i],slp) if (d>0 and o[i]<slp) else (max(o[i],slp) if d<0 and o[i]>slp else slp)
                pnl=realized + size*(((px/e0-1) if d>0 else (e0/px-1))) - fee*size
                tr.append((eb,i,d,pnl)); pos=0;led=d;leb=i; continue
            acted=False
            # 2) tier-sell (naik) — jual frac di tiap tier belum-terjual
            for k,lv in enumerate(tiers):
                if k in sold: continue
                lvl=e0*(1+lv/100) if d>0 else e0*(1-lv/100)
                reach=(h[i]>=lvl) if d>0 else (l[i]<=lvl)
                if reach and size>=frac-1e-9:
                    realized += frac*(((lvl/e0-1) if d>0 else (e0/lvl-1))) - fee*frac
                    size-=frac; sold.append(k); last_act=i; acted=True
                    if size<=1e-9:  # full scaled out = trade selesai (menang)
                        tr.append((eb,i,d,realized)); pos=0;led=d;leb=i; break
            if pos==0: continue
            # 3) re-entry pas balik ke ENTRY (bukan bar sama tier-sell; tren msh dukung)
            if reentry and not acted and i>last_act and reidx<max_re and size<1.0-1e-9:
                back=(l[i]<=e0) if d>0 else (h[i]>=e0)
                trend=(c[i]>E[i]) if d>0 else (c[i]<E[i])
                if back and trend:
                    add=1.0-size; realized-=fee*add; size=1.0; sold=[]; reidx+=1; last_act=i   # beli-balik(+fee) + re-arm
        if pos==0:
            bse=i-leb
            if LS[i] and not(led==1 and bse<cd): pos=1;e0=o[i+1] if i+1<n else c[i];eb=i;size=1.0;sold=[];reidx=0;realized=-fee;last_act=-1
            elif SS[i] and not(led==-1 and bse<cd): pos=-1;e0=o[i+1] if i+1<n else c[i];eb=i;size=1.0;sold=[];reidx=0;realized=-fee;last_act=-1
    t=pd.DataFrame(tr,columns=['eb','xb','dir','net'])
    if len(t)==0: return dict(n=0),t
    eq=np.cumprod(1+t.net.to_numpy());pk=np.maximum.accumulate(eq);dd=((pk-eq)/pk).max()*100;ret=(eq[-1]-1)*100
    yy=year[t.xb.to_numpy()];py={int(y):(np.prod(1+g.net)-1)*100 for y,g in pd.DataFrame({'y':yy,'net':t.net}).groupby('y')}
    return dict(n=len(t),ret=round(ret),dd=round(dd,1),wr=round((t.net>0).mean()*100,1),
                cal=round(ret/dd,1) if dd>0 else 0,allpos=all(v>0 for v in py.values())),t

if __name__=='__main__':
    _,t0=eng_run(df,{'add_long':aL,'add_short':aS,'tp':TPa,'sl':SLa})
    cut=int(n*0.70)
    def testcal(t):
        te=t[t.xb>=cut] if 'xb' in t else t[t.exit_bar>=cut]
        if len(te)==0:return 0
        eq=np.cumprod(1+te.net.to_numpy());pk=np.maximum.accumulate(eq);dd=((pk-eq)/pk).max()*100
        return round((eq[-1]-1)*100/dd,1) if dd>0 else 0
    print('BASE v20: ret+3327 dd11.0 wr64.3 cal303 | TESTcal 21.9')
    print()
    print('=== 4-tier POLOS (tanpa re-entry) — draft keeper ===')
    r,t=run(reentry=False); print(f'  {r} | TESTcal {testcal(t)}')
    print()
    print('=== 4-tier + PARTIAL RE-ENTRY di entry (max_re var) ===')
    for mr in [1,2,3,5]:
        r,t=run(reentry=True,max_re=mr); print(f'  max_re{mr}: {r} | TESTcal {testcal(t)}')
    print()
    print('=== variasi tier (2-tier & 3-tier) + re-entry ===')
    for tiers,fr,lbl in [((1.0,2.0),0.5,'2-tier50%'),((1.0,1.5,2.0),0.34,'3-tier'),((0.8,1.5,2.5),0.34,'3-tier wide')]:
        r,t=run(tiers=tiers,frac=fr,reentry=True,max_re=3); print(f'  {lbl}: {r} | TESTcal {testcal(t)}')
