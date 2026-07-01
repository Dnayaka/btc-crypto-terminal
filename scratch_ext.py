#!/usr/bin/env python3
"""Riset 1-Jul: pakai FAKTOR EKSTERNAL (DXY dollar-index, BTC-dominance proxy) sbg filter entry
dan/atau modulator TP/SL di v20, digabung jadi versi baru KALAU menang. Metodologi WAJIB:
full-period vs baseline (+3327/dd11/wr64.27/n557/cal303) + per-year all-positive + OOS train70/test30.

Data eksternal (fetch sekali, cache CSV):
  ext_dxy.csv  = Yahoo DX-Y.NYB daily 2016-2026 (histori PENUH, gratis, keyless).
  ext_dom.csv  = proxy BTC-dominance harian 2019-2026 dari CoinMetrics (btc / sum-16-koin-mayor,
                 SOL DIBLOK tier gratis -> proxy OVERSTATE dominance saat alt-season SOL besar,
                 tapi TREN harusnya masih valid sbg sinyal kasar).

Anti-lookahead: nilai harian dipakai TERLAMBAT 1 hari penuh (baru dipakai bar 15m di hari
BERIKUTNYA dari hari closenya) -- nilai "hari ini" belum final sampai hari itu tutup.

Teknik filter: extra_long/extra_short (AND-filter, base-breakout only di eng.py) DIGABUNG dgn
add_long/add_short (pullback OR-add) yg SUDAH di-AND filter sendiri sebelum diserahkan ke eng.run:
  extra_long = mask
  add_long   = aL & mask
  => (base & mask) | (aL & mask) = mask & (base | aL) = mask & v20_signal_penuh
Jadi filter kena ke SELURUH sinyal v20 (base+pullback), bukan cuma base breakout.
"""
import numpy as np, pandas as pd
from eng import rsi, ema, atr, signals, indicators, DEF, run as eng_run
from bot_v20_funding import pbsig, TP_BASE, TP_GENTLE, TP_WALL, SL_V20

HERE = "/home/dnayaka/Documents/dynamic_rsi/btc-terminal"
df = pd.read_csv(HERE+"/btc_15m_full.csv", parse_dates=['dt'])
o=df['open'].to_numpy(float); h=df['high'].to_numpy(float); l=df['low'].to_numpy(float); c=df['close'].to_numpy(float)
n = len(c)
R=rsi(c,DEF['rsi_len']); E=ema(c,DEF['ema_len']); A=atr(h,l,c,DEF['atr_len'])
ap=A/c*100.0; rng=h-l; body=np.where(rng>0,np.abs(c-o)/np.where(rng>0,rng,1),0.0)
aL = pbsig(o,h,l,c,R,E,ap,body,'long'); aS = pbsig(o,h,l,c,R,E,ap,body,'short')
TPa = np.full(n, TP_BASE); TPa[ap>TP_WALL] = TP_GENTLE
SLa = np.full(n, SL_V20)
bar_date = df['dt'].dt.date.to_numpy()
year = df['dt'].dt.year.to_numpy()

# ---------- muat data eksternal, hitung fitur harian LAG-1-HARI, broadcast ke bar 15m ----------
def load_ext():
    dxy = pd.read_csv(HERE+"/ext_dxy.csv")
    dxy['date'] = pd.to_datetime(dxy['ts'], unit='s').dt.date
    dxy = dxy.groupby('date', as_index=False)['dxy'].last().sort_values('date').reset_index(drop=True)
    dom = pd.read_csv(HERE+"/ext_dom.csv")
    dom['date'] = pd.to_datetime(dom['date']).dt.date
    dom = dom.sort_values('date').reset_index(drop=True)
    return dxy, dom

def roc(s, k): return s.pct_change(k)*100.0
def vs_ma(s, k): return (s/s.rolling(k).mean()-1)*100.0

def daily_feats(dxy, dom):
    dxy = dxy.copy(); dom = dom.copy()
    for k in (3,5,10,20): dxy[f'roc{k}']=roc(dxy['dxy'],k)
    dxy['vsma20']=vs_ma(dxy['dxy'],20)
    for k in (3,5,10,20): dom[f'roc{k}']=roc(dom['dom_proxy'],k)
    dom['vsma20']=vs_ma(dom['dom_proxy'],20)
    # LAG 1 hari: nilai hari D baru "diketahui"/dipakai mulai hari D+1
    dxy['use_date'] = dxy['date'] + pd.Timedelta(days=1)
    dom['use_date'] = dom['date'] + pd.Timedelta(days=1)
    return dxy, dom

def broadcast(daily, use_col_map):
    """Broadcast fitur harian (indexed by use_date) ke tiap bar 15m via merge_asof (forward-fill, no lookahead)."""
    d = daily[['use_date']+list(use_col_map.keys())].rename(columns={'use_date':'date'}).copy()
    d['date'] = pd.to_datetime(d['date'])
    d = d.sort_values('date').drop_duplicates('date')
    bd = pd.DataFrame({'date': pd.to_datetime(bar_date)})
    m = pd.merge_asof(bd, d, on='date', direction='backward')
    out = {}
    for k,newk in use_col_map.items(): out[newk] = m[k].to_numpy()
    return out

dxy_raw, dom_raw = load_ext()
dxy_d, dom_d = daily_feats(dxy_raw, dom_raw)
DX = broadcast(dxy_d, {'roc3':'dxy_roc3','roc5':'dxy_roc5','roc10':'dxy_roc10','roc20':'dxy_roc20','vsma20':'dxy_vsma20'})
DM = broadcast(dom_d, {'roc3':'dom_roc3','roc5':'dom_roc5','roc10':'dom_roc10','roc20':'dom_roc20','vsma20':'dom_vsma20'})
COV_DXY = np.mean(~np.isnan(DX['dxy_roc5']))
COV_DOM = np.mean(~np.isnan(DM['dom_roc5']))

def peryear(t):
    if len(t)==0: return {}
    yy=year[t['exit_bar'].to_numpy()]; g=pd.DataFrame({'y':yy,'net':t['net'].to_numpy()})
    return {int(y):round((np.prod(1+gg['net'])-1)*100,1) for y,gg in g.groupby('y')}

def oostest(t, cut_frac=0.70):
    if len(t)==0: return 0,0,0
    cut=int(n*cut_frac); te=t[t['exit_bar']>=cut]
    if len(te)==0: return 0,0,0
    eq=np.cumprod(1+te['net'].to_numpy()); pk=np.maximum.accumulate(eq); dd=((pk-eq)/pk).max()*100
    ret=(eq[-1]-1)*100
    return round(ret,1), round(dd,1), (round(ret/dd,1) if dd>0 else 0)

def run_filtered(mask_long=None, mask_short=None, tp_mult=None, sl_mult=None, label=""):
    """mask_long/short: bool array (True=izinkan entry). tp_mult/sl_mult: array pengali TPa/SLa (None=1)."""
    maskL = np.ones(n,bool) if mask_long is None else np.asarray(mask_long,bool)
    maskS = np.ones(n,bool) if mask_short is None else np.asarray(mask_short,bool)
    cf = dict(DEF)
    cf['extra_long']=maskL; cf['extra_short']=maskS
    cf['add_long']=aL & maskL; cf['add_short']=aS & maskS
    tp = TPa*tp_mult if tp_mult is not None else TPa
    sl = SLa*sl_mult if sl_mult is not None else SLa
    cf['tp']=tp; cf['sl']=sl
    r,t = eng_run(df, cf)
    py = peryear(t); allpos = len(py)>0 and all(v>0 for v in py.values())
    ost = oostest(t)
    return dict(label=label, ret=r['ret'], dd=r['dd'], wr=r['wr'], n=r['n'], cal=r['calmar'],
                allpos=allpos, test_ret=ost[0], test_dd=ost[1], test_cal=ost[2], years=py)

def _dir_mask(roc, long_when_neg):
    """Mask arah: long diizinkan saat roc<0 (atau >0 kalau long_when_neg=False), short kebalikannya.
    NaN (warmup/data kosong) -> True (netral, ga difilter)."""
    isnan = np.isnan(roc)
    if long_when_neg:
        mL = np.where(isnan, True, roc<0); mS = np.where(isnan, True, roc>0)
    else:
        mL = np.where(isnan, True, roc>0); mS = np.where(isnan, True, roc<0)
    return mL, mS

if __name__ == "__main__":
    print(f"BTC 15m n={n} | DXY coverage={COV_DXY:.1%} | DOM coverage={COV_DOM:.1%}")
    print("REF v20 baseline: ret+3327 dd11.0 wr64.27 n557 cal303.1 | TEST21.9\n")

    print("=== A) BASELINE (harus == v20 persis) ===")
    b = run_filtered(label="baseline")
    print(f"  ret{b['ret']:+.0f} dd{b['dd']} wr{b['wr']} n{b['n']} cal{b['cal']} allpos={b['allpos']} | TEST ret{b['test_ret']:+.0f} dd{b['test_dd']} cal{b['test_cal']}")

    print("\n=== B) DXY-direction filter (long saat dollar melemah, short saat dollar menguat) ===")
    for k in (3,5,10,20):
        mL, mS = _dir_mask(DX[f'dxy_roc{k}'], long_when_neg=True)
        r = run_filtered(mL, mS, label=f"dxy_roc{k}_dir")
        print(f"  ROC{k}d: ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['cal']} allpos={r['allpos']} | TEST ret{r['test_ret']:+.0f} dd{r['test_dd']} cal{r['test_cal']}")
    mL, mS = _dir_mask(DX['dxy_vsma20'], long_when_neg=True)
    r=run_filtered(mL,mS,label="dxy_vsma20_dir")
    print(f"  vsMA20: ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['cal']} allpos={r['allpos']} | TEST ret{r['test_ret']:+.0f} dd{r['test_dd']} cal{r['test_cal']}")

    print("\n=== C) DXY-direction TERBALIK (kontrol -- kalau B menang krn edge asli, C harus kalah) ===")
    for k in (5,10):
        mL, mS = _dir_mask(DX[f'dxy_roc{k}'], long_when_neg=False)
        r = run_filtered(mL, mS, label=f"dxy_roc{k}_inv")
        print(f"  ROC{k}d-INV: ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['cal']} allpos={r['allpos']} | TEST ret{r['test_ret']:+.0f} dd{r['test_dd']} cal{r['test_cal']}")

    print("\n=== D) Dominance-direction filter (2 arah, empiris -- hipotesis ga jelas arahnya) ===")
    for k in (5,10,20):
        for tag, long_when_neg in [("dom_naik=long", False), ("dom_turun=long", True)]:
            mL, mS = _dir_mask(DM[f'dom_roc{k}'], long_when_neg=long_when_neg)
            r = run_filtered(mL, mS, label=f"dom{k}_{tag}")
            print(f"  {tag} k={k}: ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['cal']} allpos={r['allpos']} | TEST ret{r['test_ret']:+.0f} dd{r['test_dd']} cal{r['test_cal']}")

    print("\n=== E) TP/SL modulasi oleh rezim DXY (kuat = |roc10| tinggi) ===")
    dxy_roc10 = DX['dxy_roc10']
    strong_dollar = np.where(np.isnan(dxy_roc10), False, np.abs(dxy_roc10) > np.nanpercentile(dxy_roc10, 70))
    for tpm, slm, tag in [(1.15,1.0,"TP+15%_saat_dxy_kuat"), (0.85,1.0,"TP-15%_saat_dxy_kuat"), (1.0,0.85,"SL-15%_saat_dxy_kuat")]:
        tp_mult = np.where(strong_dollar, tpm, 1.0); sl_mult = np.where(strong_dollar, slm, 1.0)
        r = run_filtered(tp_mult=tp_mult, sl_mult=sl_mult, label=tag)
        print(f"  {tag}: ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['cal']} allpos={r['allpos']} | TEST ret{r['test_ret']:+.0f} dd{r['test_dd']} cal{r['test_cal']}")

    print("\n=== F) Kombinasi DXY+DOM SEPAKAT (filter lebih ketat) ===")
    dxy5=DX['dxy_roc5']; dom5=DM['dom_roc5']
    both_nan = np.isnan(dxy5) | np.isnan(dom5)
    mL = np.where(both_nan, True, (dxy5<0)&(dom5<0))
    mS = np.where(both_nan, True, (dxy5>0)&(dom5>0))
    r = run_filtered(mL, mS, label="combo_dxy_dom_agree")
    print(f"  combo: ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['cal']} allpos={r['allpos']} | TEST ret{r['test_ret']:+.0f} dd{r['test_dd']} cal{r['test_cal']}")
