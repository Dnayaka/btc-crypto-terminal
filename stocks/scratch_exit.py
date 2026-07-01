#!/usr/bin/env python3
import sys; sys.path.insert(0, "/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks")
import itertools, json
import numpy as np, pandas as pd
import pf, seng

DATA = pf.load_data()
print(f"[snapshot] {len(DATA)} symbols loaded")

def metrics(cf_over, K=5, lev=1.0):
    cf = dict(pf.CAND); cf.update(cf_over)
    T = pf.all_trades(DATA, cf)
    full = pf.stats(T)
    Th = T[T['ed']>=np.datetime64('2024-01-01')]
    hold = pf.stats(T[T['xd']>=np.datetime64('2024-01-01')])
    py = pf.per_year(T); pmin = min(py.values()) if py else 0.0
    p  = pf.portfolio(T, K=K, lev=lev)
    ph = pf.portfolio(Th, K=K, lev=lev, start='2024-01-01')
    return dict(wr=full['wr'], mean=full['mean'], n=full['n'], pf=full['pf'],
                hmean=hold['mean'], hwr=hold['wr'],
                cagr=p['cagr'], dd=p['dd'], hcagr=ph['cagr'], hdd=ph['dd'],
                pmin=pmin, py={k:round(v,2) for k,v in py.items()})

def show(tag,r):
    print(f"{tag:28s} cagr={r['cagr']:5.2f} dd={r['dd']:4.1f} | hcagr={r['hcagr']:5.2f} hdd={r['hdd']:4.1f} "
          f"| wr={r['wr']:4.1f} mean={r['mean']:.3f} hmean={r['hmean']:+.3f} pmin={r['pmin']:+.2f} n={r['n']:3d}")

# ---------- partial-TP + runner (blended single-row per entry) ----------
def all_trades_partial(data, cf, tp_partial, frac=0.5):
    """One trade row per entry. Position scales out frac at +tp_partial%; remainder
    rides runner-exit (cf without TP: SMA-signal/RSI/maxhold/optional trail).
    net = frac*legA + (1-frac)*legB. Entries identical to runner pass (no TP) so
    re-entry timing is consistent within the row set."""
    fb,fs = seng.DEF['fee_buy'], seng.DEF['fee_sell']
    rows=[]
    runcf = dict(pf.CAND); runcf.update(cf); runcf['tp']=0.0  # build on CAND base (sl=20 etc)
    for sym,df in data.items():
        try:
            cfx=dict(seng.DEF); cfx.update(runcf)
            ind=seng.indicators(df,cfx)
            _,t=seng.run(df,runcf)
        except Exception: continue
        if not len(t): continue
        o=ind['o']; h=ind['h']
        dts=df['dt'].to_numpy()
        for _,r in t.iterrows():
            eb=int(r['eb']); xb=int(r['xb']); entry=float(r['entry'])
            netB=float(r['net'])                       # runner leg (full lifecycle)
            tpx=entry*(1+tp_partial/100.0)
            # find first bar in (eb..xb] where high>=tpx -> partial fill
            netA=netB
            for i in range(eb,xb+1):
                if h[i]>=tpx:
                    px=max(o[i],tpx) if o[i]>tpx else tpx
                    netA=(px/entry)*(1-fs)/(1+fb)-1.0
                    break
            net=frac*netA+(1-frac)*netB
            rows.append((dts[eb],dts[xb],net,sym))
    return pd.DataFrame(rows,columns=['ed','xd','net','sym'])

def metrics_T(T,K=5,lev=1.0):
    full=pf.stats(T)
    hold=pf.stats(T[T['xd']>=np.datetime64('2024-01-01')])
    py=pf.per_year(T); pmin=min(py.values()) if py else 0.0
    p=pf.portfolio(T,K=K,lev=lev)
    Th=T[T['ed']>=np.datetime64('2024-01-01')]; ph=pf.portfolio(Th,K=K,lev=lev,start='2024-01-01')
    return dict(wr=full['wr'],mean=full['mean'],n=full['n'],pf=full['pf'],hmean=hold['mean'],hwr=hold['wr'],
                cagr=p['cagr'],dd=p['dd'],hcagr=ph['cagr'],hdd=ph['dd'],pmin=pmin,py={k:round(v,2) for k,v in py.items()})

if __name__=='__main__':
    show("BASELINE(CAND)", metrics({}))
    print("-- finalists (engine TP/maxhold/sma_exit) --")
    cands={
      "se5_mh7_tp6":  dict(sma_exit=5,max_hold=7, tp=6.0),
      "se4_mh10_tp6": dict(sma_exit=4,max_hold=10,tp=6.0),
      "se5_mh10_tp6": dict(sma_exit=5,max_hold=10,tp=6.0),
      "se4_mh12_tp6": dict(sma_exit=4,max_hold=12,tp=6.0),
      "se5_mh10_tp7": dict(sma_exit=5,max_hold=10,tp=7.0),
      "se5_mh10_tp8": dict(sma_exit=5,max_hold=10,tp=8.0),
    }
    fin={}
    for tag,cf in cands.items():
        r=metrics(cf); fin[tag]=r; show(tag,r)

    print("\n-- tp-neighbor robustness for se4_mh10 & se5_mh10 (CAGR) --")
    for se in (4,5):
        line=f"se{se}_mh10: "
        for tp in (4,5,6,7,8):
            r=metrics(dict(sma_exit=se,max_hold=10,tp=float(tp)))
            line+=f"tp{tp}={r['cagr']:.2f}(dd{r['dd']:.0f},wr{r['wr']:.0f}) "
        print(line)

    print("\n-- partial-TP + runner (scale out frac @ +X%, remainder SMA-exit runner) --")
    # sanity: tp_partial huge -> should ~= pure runner (tp=0)
    Tr=all_trades_partial(DATA, dict(sma_exit=5,max_hold=10), tp_partial=999, frac=0.5)
    show("runner_only(tp0 check)", metrics_T(Tr))
    for frac in (0.5,):
        for tpp in (5,6,8,10):
            for se,mh in [(5,10),(4,10)]:
                T=all_trades_partial(DATA, dict(sma_exit=se,max_hold=mh), tp_partial=tpp, frac=frac)
                r=metrics_T(T)
                show(f"part{tpp}_f{frac}_se{se}_mh{mh}", r)

    print("\n-- PERTURB gate (entry-robustness; varies rsi_len/buy/sma_exit) --")
    for tag,cf in [("se5_mh7_tp6",dict(sma_exit=5,max_hold=7,tp=6.0)),
                   ("se4_mh10_tp6",dict(sma_exit=4,max_hold=10,tp=6.0)),
                   ("se5_mh10_tp6",dict(sma_exit=5,max_hold=10,tp=6.0)),
                   ("BASE",{})]:
        print(f"  {tag:16s} perturb={pf.perturb(cf,DATA)}")
