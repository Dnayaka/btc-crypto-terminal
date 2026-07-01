#!/usr/bin/env python3
"""Riset 1-Jul: user lihat 4x SL beruntun, curiga berbarengan volatilitas Fed/DXY -> coba MINIMALISIR
lewat filter jam MACRO-EVENT (FOMC decision + NFP release), BUKAN filter arah DXY (itu udah gagal,
lihat scratch_ext.py - kontrol arah-terbalik hasilnya mirip = DXY-direction ga ada edge nyata).

Ide beda: candle di JAM RILIS macro-event sering ekstrem-liar (whipsaw), entry yg START tepat di jam
itu rawan kena snapback cepat -> SL. Coba: (A) skip entry baru dlm jendela +-N jam macro-event,
(B) lebar-in SL dlm jendela itu (biar ga kena snapback tipis), (C) A+B gabung.

FOMC decision dates 2019-2026: diverifikasi WebFetch federalreserve.gov/monetarypolicy/fomccalendars.htm
+ press release 2019/2020 (monetary20180525a.htm / monetary20190517a.htm). Jam = 14:00 ET (DST-aware).
NFP: Jumat pertama tiap bulan, 08:30 ET (DST-aware) -- rilis BLS reguler, tak perlu API.

Metodologi WAJIB (sama sesi ini): full-period vs baseline (+3327/dd11/wr64.27/n557/cal303) +
per-year all-positive + OOS train70/test30.
"""
import numpy as np, pandas as pd, datetime
from zoneinfo import ZoneInfo
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
year = df['dt'].dt.year.to_numpy()
bar_ts = df['dt'].to_numpy()   # tz-aware UTC (dari CSV, cek dtype)

# ---------- FOMC decision dates (verified federalreserve.gov, 2019-2026) ----------
FOMC_DATES = [
 (2019,1,30),(2019,3,20),(2019,5,1),(2019,6,19),(2019,7,31),(2019,9,18),(2019,10,30),(2019,12,11),
 (2020,1,29),(2020,3,18),(2020,4,29),(2020,6,10),(2020,7,29),(2020,9,16),(2020,11,5),(2020,12,16),
 (2021,1,27),(2021,3,17),(2021,4,28),(2021,6,16),(2021,7,28),(2021,9,22),(2021,11,3),(2021,12,15),
 (2022,1,26),(2022,3,16),(2022,5,4),(2022,6,15),(2022,7,27),(2022,9,21),(2022,11,2),(2022,12,14),
 (2023,2,1),(2023,3,22),(2023,5,3),(2023,6,14),(2023,7,26),(2023,9,20),(2023,11,1),(2023,12,13),
 (2024,1,31),(2024,3,20),(2024,5,1),(2024,6,12),(2024,7,31),(2024,9,18),(2024,11,7),(2024,12,18),
 (2025,1,29),(2025,3,19),(2025,5,7),(2025,6,18),(2025,7,30),(2025,9,17),(2025,10,29),(2025,12,10),
 (2026,1,28),(2026,3,18),(2026,4,29),(2026,6,17),
]
def fomc_utc():
    out=[]
    for y,mo,d in FOMC_DATES:
        dt=datetime.datetime(y,mo,d,14,0,tzinfo=ZoneInfo("America/New_York"))
        out.append(dt.astimezone(datetime.timezone.utc))
    return out

def nfp_utc(start_year=2019, end_year=2026):
    out=[]
    for y in range(start_year,end_year+1):
        for mo in range(1,13):
            if y==end_year and mo>7: break
            d=datetime.date(y,mo,1)
            while d.weekday()!=4: d+=datetime.timedelta(days=1)   # Jumat pertama
            dt=datetime.datetime(d.year,d.month,d.day,8,30,tzinfo=ZoneInfo("America/New_York"))
            out.append(dt.astimezone(datetime.timezone.utc))
    return out

FOMC_TS = fomc_utc(); NFP_TS = nfp_utc()
print(f"FOMC events: {len(FOMC_TS)} | NFP events: {len(NFP_TS)}")

def macro_mask(hours_before, hours_after, events):
    """True di bar yg dlm jendela [-hours_before, +hours_after] jam dari SALAH SATU event."""
    bt = pd.to_datetime(bar_ts, utc=True)
    m = np.zeros(n, bool)
    for e in events:
        e = pd.Timestamp(e)
        lo = e - pd.Timedelta(hours=hours_before); hi = e + pd.Timedelta(hours=hours_after)
        m |= np.asarray((bt >= lo) & (bt <= hi))
    return m

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

def run_variant(mask_block=None, sl_mult=None, label=""):
    """mask_block: True=BLOK entry baru di bar ini. sl_mult: array pengali SLa (None=1x)."""
    maskL = np.ones(n,bool) if mask_block is None else ~mask_block
    cf = dict(DEF)
    cf['extra_long']=maskL; cf['extra_short']=maskL
    cf['add_long']=aL & maskL; cf['add_short']=aS & maskL
    sl = SLa*sl_mult if sl_mult is not None else SLa
    cf['tp']=TPa; cf['sl']=sl
    r,t = eng_run(df, cf)
    py = peryear(t); allpos = len(py)>0 and all(v>0 for v in py.values())
    ost = oostest(t)
    return dict(label=label, ret=r['ret'], dd=r['dd'], wr=r['wr'], n=r['n'], cal=r['calmar'],
                allpos=allpos, test_ret=ost[0], test_dd=ost[1], test_cal=ost[2])

if __name__ == "__main__":
    print("REF v20 baseline: ret+3327 dd11.0 wr64.27 n557 cal303.1 | TEST21.9\n")
    print("=== A) BASELINE ===")
    b = run_variant(label="baseline")
    print(f"  ret{b['ret']:+.0f} dd{b['dd']} wr{b['wr']} n{b['n']} cal{b['cal']} allpos={b['allpos']} | TEST ret{b['test_ret']:+.0f} dd{b['test_dd']} cal{b['test_cal']}")

    print("\n=== B) SKIP entry baru dlm jendela FOMC (macro decision paling liar) ===")
    for hb,ha in [(0,1),(0,2),(1,2),(2,2)]:
        mask = macro_mask(hb, ha, FOMC_TS)
        r = run_variant(mask_block=mask, label=f"fomc-{hb}/+{ha}h")
        print(f"  -{hb}h/+{ha}h ({mask.mean()*100:.2f}% bar terblok): ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['cal']} allpos={r['allpos']} | TEST ret{r['test_ret']:+.0f} dd{r['test_dd']} cal{r['test_cal']}")

    print("\n=== C) SKIP entry baru dlm jendela NFP ===")
    for hb,ha in [(0,1),(0,2),(1,2)]:
        mask = macro_mask(hb, ha, NFP_TS)
        r = run_variant(mask_block=mask, label=f"nfp-{hb}/+{ha}h")
        print(f"  -{hb}h/+{ha}h ({mask.mean()*100:.2f}% bar terblok): ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['cal']} allpos={r['allpos']} | TEST ret{r['test_ret']:+.0f} dd{r['test_dd']} cal{r['test_cal']}")

    print("\n=== D) SKIP entry baru dlm jendela FOMC+NFP gabungan ===")
    for hb,ha in [(0,2),(1,2),(2,3)]:
        mask = macro_mask(hb, ha, FOMC_TS) | macro_mask(hb, ha, NFP_TS)
        r = run_variant(mask_block=mask, label=f"combo-{hb}/+{ha}h")
        print(f"  -{hb}h/+{ha}h ({mask.mean()*100:.2f}% bar terblok): ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['cal']} allpos={r['allpos']} | TEST ret{r['test_ret']:+.0f} dd{r['test_dd']} cal{r['test_cal']}")

    print("\n=== E) LEBARIN SL (bukan blok entry) dlm jendela FOMC+NFP -2/+3h ===")
    mask = macro_mask(2,3,FOMC_TS) | macro_mask(2,3,NFP_TS)
    for mult,tag in [(1.3,"SL+30%"),(1.5,"SL+50%"),(2.0,"SL+100%")]:
        slm = np.where(mask, mult, 1.0)
        r = run_variant(sl_mult=slm, label=tag)
        print(f"  {tag} ({mask.mean()*100:.2f}% bar kena): ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['cal']} allpos={r['allpos']} | TEST ret{r['test_ret']:+.0f} dd{r['test_dd']} cal{r['test_cal']}")

    print("\n=== F) KONTROL: blok jam ACAK (jumlah bar sama dgn D terbaik) -- kalau F≈D, bukan macro-event yg berperan ===")
    best_frac = macro_mask(1,2,FOMC_TS).mean() + macro_mask(1,2,NFP_TS).mean()
    rng_ctrl = np.random.RandomState(42)
    rand_mask = rng_ctrl.random(n) < best_frac
    r = run_variant(mask_block=rand_mask, label="random-ctrl")
    print(f"  random {best_frac*100:.2f}% blok: ret{r['ret']:+.0f} dd{r['dd']} wr{r['wr']} n{r['n']} cal{r['cal']} allpos={r['allpos']} | TEST ret{r['test_ret']:+.0f} dd{r['test_dd']} cal{r['test_cal']}")
