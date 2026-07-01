#!/usr/bin/env python3
import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import numpy as np, pandas as pd, itertools, json
import pf, seng, glob, os

# FROZEN snapshot (background fetch keeps adding symbols/rows to data/; pin to original 48 for
# reproducible, apples-to-apples comparison vs the orchestrator baseline).
SNAP="/tmp/claude-1000/-home-dnayaka/38e6bacd-d0e9-4982-be14-2d9c4c3936b3/scratchpad/snap"
FROZEN48=set("ACES ADRO AKRA AMMN AMRT ANTM ARTO ASII BBCA BBNI BBRI BMRI BRIS BRPT BSDE BTPS "
    "BUKA CPIN CTRA EMTK EXCL GGRM GOTO HMSP ICBP INCO INDF INKP INTP ISAT ITMG JSMR KLBF MAPI "
    "MDKA MEDC MTEL MYOR PGAS PTBA PWON SIDO SMGR TLKM TOWR TPIA UNTR UNVR".split())
def load_snap():
    d={}; files=glob.glob(os.path.join(SNAP,"*.JK.csv"))
    if files:                              # frozen snapshot present
        for f in files:
            sym=os.path.basename(f)[:-4]; x=pd.read_csv(f,parse_dates=['dt'])
            if len(x)>=300: d[sym]=x
        return d
    for f in glob.glob(os.path.join(pf.DATA,"*.JK.csv")):  # fallback: pin to original 48
        sym=os.path.basename(f)[:-4]
        if sym not in FROZEN48: continue
        x=pd.read_csv(f,parse_dates=['dt'])
        if len(x)>=300: d[sym]=x
    return d
data = load_snap()
print(f"[frozen snapshot: {len(data)} symbols]")

# ---------- per-symbol OR-mask of oversold triggers ----------
def down_streak(c):
    """consecutive down-close days ending at i (close[i]<close[i-1])."""
    down = np.zeros(len(c), bool)
    down[1:] = c[1:] < c[:-1]
    s = np.zeros(len(c), int); run = 0
    for i in range(len(c)):
        run = run+1 if down[i] else 0
        s[i] = run
    return s

def build_mask(df, p):
    """p = dict of trigger params; missing trigger -> disabled. Returns OR union mask."""
    c = df['close'].to_numpy(float); l = df['low'].to_numpy(float)
    n = len(c); m = np.zeros(n, bool)
    if p.get('r2') is not None:
        m |= (seng.rsi(c,2) < p['r2'])
    if p.get('r4') is not None:
        m |= (seng.rsi(c,4) < p['r4'])
    if p.get('rN') is not None:   # generic RSI len/thr
        m |= (seng.rsi(c,p['rN'][0]) < p['rN'][1])
    if p.get('smad') is not None: # close < SMA(smaL)*(1-k)
        sL,k = p['smad']; s = seng.sma(c,sL)
        m |= (c < s*(1-k/100.0))
    if p.get('streak') is not None:
        m |= (down_streak(c) >= p['streak'])
    if p.get('bb') is not None:   # low <= lowerBB(len,kk)
        bl_len,kk = p['bb']; bm = seng.sma(c,bl_len)
        bsd = pd.Series(c).rolling(bl_len).std(ddof=0).to_numpy()
        m |= (l <= (bm - kk*bsd))
    return m

def build_mask_conf(df, p):
    """oversold (RSI len<thr) AND optional reversal confirmation.
    p: rlen,rthr ; conf in {None,'green','up','greenup'} ; also OR a deep unconditional RSI via p['deep']=(len,thr)."""
    c=df['close'].to_numpy(float); o=df['open'].to_numpy(float)
    n=len(c); R=seng.rsi(c,p['rlen'])
    cond=(R<p['rthr'])
    conf=p.get('conf')
    if conf in ('green','greenup'):
        cond &= (c>o)
    if conf in ('up','greenup'):
        up=np.zeros(n,bool); up[1:]=c[1:]>c[:-1]; cond &= up
    if p.get('deep') is not None:
        dl,dt=p['deep']; cond |= (seng.rsi(c,dl)<dt)
    return cond

def build_mask_filt(df, p):
    """oversold(rlen<rthr) [OR deep] AND trend-quality filters to lift WR.
    filters: above_sf=L (c>SMA L), sf_rise=(L,k) SMA L rising over k, st_rise=k SMA200 rising,
             dist200=m (c>=SMA200*(1+m/100)), notlow=N (c not the N-day min)."""
    c=df['close'].to_numpy(float); n=len(c)
    cond=(seng.rsi(c,p['rlen'])<p['rthr'])
    if p.get('deep') is not None:
        dl,dt=p['deep']; cond |= (seng.rsi(c,dl)<dt)
    if p.get('above_sf') is not None:
        cond &= (c > seng.sma(c,p['above_sf']))
    if p.get('sf_rise') is not None:
        L,k=p['sf_rise']; s=seng.sma(c,L); sp=np.roll(s,k); cond &= (s>sp)
    if p.get('st_rise') is not None:
        k=p['st_rise']; s=seng.sma(c,200); sp=np.roll(s,k); cond &= (s>sp)
    if p.get('dist200') is not None:
        s=seng.sma(c,200); cond &= (c >= s*(1+p['dist200']/100.0))
    if p.get('notlow') is not None:
        N=p['notlow']; mn=seng.rollmin(c,N); cond &= (c > mn)
    return cond

def trades(maskp, cf_over=None, builder=build_mask, dat=None):
    cf = dict(pf.CAND); cf['rsi_buy'] = 100.0   # disable base RSI gate; mask drives entry
    if cf_over: cf.update(cf_over)
    rows=[]
    for sym,df in (dat or data).items():
        m = builder(df, maskp)
        c2 = dict(cf); c2['extra_long'] = m
        try: _,t = seng.run(df,c2)
        except Exception: continue
        if not len(t): continue
        dts = df['dt'].to_numpy()
        for _,r in t.iterrows():
            rows.append((dts[int(r['eb'])],dts[int(r['xb'])],float(r['net']),sym))
    return pd.DataFrame(rows,columns=['ed','xd','net','sym'])

def ev(maskp, cf_over=None, K=5, lev=1.0, tag="", builder=build_mask, dat=None):
    T = trades(maskp, cf_over, builder=builder, dat=dat)
    full = pf.stats(T)
    hold = pf.stats(T[T['xd']>=np.datetime64('2024-01-01')])
    py = pf.per_year(T); pmin = min(py.values()) if py else 0.0
    port = pf.portfolio(T,K=K,lev=lev)
    return dict(tag=tag,full=full,hold=hold,port=port,pmin=pmin,py=py,
                nsym=int((T.groupby('sym')['net'].sum()>0).sum()) if len(T) else 0)

def show(r):
    f=r['full']; h=r['hold']; p=r['port']
    print(f"{r['tag']:28s} n={f['n']:4d} WR={f['wr']:5.1f} mean={f['mean']:+.3f} pf={f['pf']:.2f} | "
          f"hoWR={h['wr']:5.1f} hoMean={h['mean']:+.3f} | CAGR={p['cagr']:5.2f} DD={p['dd']:4.1f} "
          f"tk={p['taken']} sk={p['skip']} | pmin={r['pmin']:+.2f} nsym={r['nsym']}")

def evc(p, tag): show(ev(p, tag=tag, builder=build_mask_conf))

def eval_cf(cf_over, tag, K=5, lev=1.0):
    """Evaluate a standard mr_rsi cf override on the FROZEN data (uses pf.all_trades)."""
    cf=dict(pf.CAND); cf.update(cf_over or {})
    T=pf.all_trades(data,cf)
    full=pf.stats(T); hold=pf.stats(T[T['xd']>=np.datetime64('2024-01-01')])
    py=pf.per_year(T); pmin=min(py.values()) if py else 0.0
    port=pf.portfolio(T,K=K,lev=lev)
    r=dict(tag=tag,full=full,hold=hold,port=port,pmin=pmin,py=py,
           nsym=int((T.groupby('sym')['net'].sum()>0).sum()) if len(T) else 0)
    show(r); return r

def eval_cf_dat(cf_over, tag, dat, K=5, lev=1.0):
    cf=dict(pf.CAND); cf.update(cf_over or {})
    T=pf.all_trades(dat,cf)
    full=pf.stats(T); hold=pf.stats(T[T['xd']>=np.datetime64('2024-01-01')])
    py=pf.per_year(T); pmin=min(py.values()) if py else 0.0
    port=pf.portfolio(T,K=K,lev=lev)
    return dict(tag=tag,full=full,hold=hold,port=port,pmin=pmin,py=py,
                nsym=int((T.groupby('sym')['net'].sum()>0).sum()) if len(T) else 0)

if __name__=='__main__':
    print("=== BASELINE on frozen snapshot (should match orchestrator ~66.3/6.23) ===")
    eval_cf({}, "baseline mr_rsi CAND")
    def evf(p,tag,**kw): show(ev(p,tag=tag,builder=build_mask_filt,**kw))

    # ---- FINAL WINNER ----
    WIN = dict(rlen=4, rthr=19, deep=(2,5), sf_rise=(50,5))
    print("=== WINNER: (r4<19 OR r2<5) & SMA50rise5 ===")
    r=ev(WIN,builder=build_mask_filt,tag="WINNER")
    show(r); print("   per_year:",{k:round(v,2) for k,v in r['py'].items()})

    print("\n=== custom PERTURBATION (mask params + exit), pf-style pass = mean>0 & WR>=60 ===")
    npass60=npass65=ntot=0; cagrs=[]; worst=None
    for rthr in [18,19,20]:
        for dr in [4,5,6]:
            for k in [3,5,8]:
                for L in [40,50,60]:
                    for se in [4,5,6]:
                        p=dict(rlen=4,rthr=rthr,deep=(2,dr),sf_rise=(L,k))
                        rr=ev(p,cf_over=dict(sma_exit=se),builder=build_mask_filt,tag="")
                        f=rr['full']; ntot+=1
                        ok60=(f['mean']>0 and f['wr']>=60); ok65=(f['mean']>0 and f['wr']>=65)
                        npass60+=ok60; npass65+=ok65; cagrs.append(rr['port']['cagr'])
                        if worst is None or rr['port']['cagr']<worst[1]: worst=(p,rr['port']['cagr'],f['wr'])
    print(f"  neighbors={ntot}  pass(WR>=60)={npass60/ntot:.2f}  pass(WR>=65)={npass65/ntot:.2f}")
    print(f"  CAGR neighborhood: min={min(cagrs):.2f} med={np.median(cagrs):.2f} max={max(cagrs):.2f}")

    print("\n=== OUT-OF-UNIVERSE: 28 NEW symbols (added by fetch, UNSEEN in tuning) ===")
    cur={}
    for f in glob.glob(os.path.join(pf.DATA,"*.JK.csv")):
        sym=os.path.basename(f)[:-4]
        try:
            x=pd.read_csv(f,parse_dates=['dt'])
            if len(x)>=300: cur[sym]=x
        except Exception: pass
    new={s:df for s,df in cur.items() if s not in data}
    print(f"  current universe={len(cur)}  new(unseen)={len(new)}")
    if new:
        show(ev(WIN,builder=build_mask_filt,tag="WINNER on NEW syms",dat=new))
        show(eval_cf_dat({}, "BASELINE on NEW syms", new))
    show(ev(WIN,builder=build_mask_filt,tag="WINNER on ALL current",dat=cur))
    show(eval_cf_dat({}, "BASELINE on ALL current", cur))
