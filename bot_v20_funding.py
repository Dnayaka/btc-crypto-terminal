#!/usr/bin/env python3
"""bot_v20_funding.py — LIBRARY + runner sleeve v20 (RSI-momentum breakout + pullback +
regime-TP). Sleeve funding & CVD DIHAPUS (28-Jun, permintaan user): sekarang v20-ONLY.

Sleeve v20 = SAMA persis dgn version20_pullback_regimeTP.pine. Dijalankan tiap close bar
15m (cron) -> generate sinyal/posisi; DRY-RUN/alert default (live via bot_config.json).

Nama file dipertahankan agar import & service tak putus; isinya kini murni v20.

PEMAKAIAN:
  python3 bot_v20_funding.py --selftest   # replay CSV, buktikan bot==backtest eng.py
  python3 bot_v20_funding.py --status     # posisi & equity paper saat ini
  python3 bot_v20_funding.py --once       # proses bar terbaru (cron 15m, backfill bar terlewat)

EKSEKUSI ASLI: default live=false (cuma sinyal). Live diatur via bot_config.json (admin
localhost:8789). Leverage WAJIB <=1x (riset: 2x = DD 2x + risiko likuidasi).
"""
import os, sys, json, time, argparse
import numpy as np, pandas as pd
import requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from eng import rsi, ema, atr, signals, DEF, run as eng_run

# ===================== KONFIG =====================
HERE      = "/home/dnayaka/Documents/dynamic_rsi/btc-terminal"
SYMBOL    = "BTCUSDT"
INTERVAL  = "15m"
BAR_MS    = 15*60*1000
CAPITAL   = float(os.environ.get("BOT_CAPITAL", 1000.0))   # modal total (USDT)
LEVERAGE  = 1.0                                            # WAJIB <=1x
DRY_RUN   = True                                           # True = cuma sinyal, TIDAK trade asli
WEBHOOK   = os.environ.get("BOT_WEBHOOK", "")              # opsional: POST sinyal ke URL
STATE_F   = os.path.join(HERE, "bot_state.json")
VERIFY    = os.environ.get("FETCH_VERIFY","0")=="1"
LOCK_F    = os.path.join(HERE, "bot.lock")
import fcntl
def acquire_lock():
    """Lock antar-proses (flock non-blocking). Return handle kalau dapat, None kalau run lain jalan.
    CEGAH DOUBLE-ORDER saat cron overlap (run > slot 15m -> 2 proses baca posisi flat -> 2x open)."""
    f=open(LOCK_F,"w")
    try: fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB); return f
    except (BlockingIOError,OSError): f.close(); return None
def release_lock(f):
    if f:
        try: fcntl.flock(f, fcntl.LOCK_UN); f.close()
        except Exception: pass

# ===================== LOG TERPISAH (run vs error) =====================
import logging as _lg
_LOGDIR=os.path.join(HERE,"logs")
try: os.makedirs(_LOGDIR, exist_ok=True)
except Exception: pass
def _mklog():
    lg=_lg.getLogger("bot_v20"); lg.setLevel(_lg.INFO); lg.handlers=[]; lg.propagate=False
    fmt=_lg.Formatter("%(asctime)s %(levelname)-5s %(message)s","%Y-%m-%d %H:%M:%S")
    rh=_lg.FileHandler(os.path.join(_LOGDIR,"bot_run.log")); rh.setLevel(_lg.INFO)
    rh.addFilter(lambda r: r.levelno < _lg.ERROR); rh.setFormatter(fmt)   # run log: INFO/WARN aja (error dipisah)
    eh=_lg.FileHandler(os.path.join(_LOGDIR,"bot_err.log")); eh.setLevel(_lg.ERROR); eh.setFormatter(fmt)
    lg.addHandler(rh); lg.addHandler(eh); return lg
LOG=_mklog()
def log_run(msg):
    try: LOG.info(msg)
    except Exception: pass
def log_err(msg):
    try: LOG.error(msg)
    except Exception: pass
# v20 exit (sama dgn version20 pine / DEF)
TP_BASE, TP_GENTLE, TP_WALL, SL_V20 = 2.0, 2.15, 0.40, 1.9
COOLDOWN = 6
PB_W = 28
SESS = requests.Session()

# ===================== MACRO-EVENT SL WIDENING (FOMC + NFP) =====================
# Port dari version20_1_pullback_regimeTP.pine (2-Jul) -- riset 1-Jul (harness eng.py 558 trade
# 2019-2026): cal 297->308, WR+0.2pt, DD SAMA PERSIS 10.97 (macro-window cuma ~1% bar), OOS-test
# cal 21.2->22.7. Sebelum port ini, LIVE BOT TAK PUNYA fitur ini (cuma pine yg divalidasi) --
# ketahuan 2-Jul saat cross-check pine vs python, execution diam-diam beda dari yg didoc.
# ⚠ MAINTENANCE: array ini HARUS disinkron manual dgn fomc_dk di file .pine (perpanjang bareng
# tiap akhir tahun -- pine punya alarm auto kalau lupa, python ini TIDAK, jadi WAJIB ingat).
FOMC_DATES = [
 20190130,20190320,20190501,20190619,20190731,20190918,20191030,20191211,
 20200129,20200318,20200429,20200610,20200729,20200916,20201105,20201216,
 20210127,20210317,20210428,20210616,20210728,20210922,20211103,20211215,
 20220126,20220316,20220504,20220615,20220727,20220921,20221102,20221214,
 20230201,20230322,20230503,20230614,20230726,20230920,20231101,20231213,
 20240131,20240320,20240501,20240612,20240731,20240918,20241107,20241218,
 20250129,20250319,20250507,20250618,20250730,20250917,20251029,20251210,
 20260128,20260318,20260429,20260617,20260729,20260916,20261028,20261209,
 20270127,20270317,20270428,20270609,20270728,20270915,20271027,20271208,
]
FOMC_SET = set(FOMC_DATES)
MACRO_MULT, MACRO_BEFORE, MACRO_AFTER = 1.3, 2, 3

def macro_sl_mult(dt_utc):
    """Array pengali SL per-bar (1.0 normal, MACRO_MULT saat jendela FOMC 14:00 ET / NFP 08:30 ET).
    dt_utc: pandas Series datetime tz-aware UTC (df['dt']). Faithful port pine `in_macro_window`."""
    et = dt_utc.dt.tz_convert("America/New_York")
    dk = et.dt.year*10000 + et.dt.month*100 + et.dt.day
    h  = et.dt.hour
    is_fomc = dk.isin(FOMC_SET)
    is_nfp  = (et.dt.dayofweek==4) & (et.dt.day<=7)          # Jumat pertama tiap bulan (dayofweek: Jumat=4)
    in_fomc = is_fomc & (h>=14-MACRO_BEFORE) & (h<=14+MACRO_AFTER)
    in_nfp  = is_nfp  & (h>=8-MACRO_BEFORE)  & (h<=8+MACRO_AFTER)
    return np.where(in_fomc|in_nfp, MACRO_MULT, 1.0)

# ===================== SINYAL =====================
def pbsig(o,h,l,c,R,E,ap,body,side,W=PB_W):
    """Pullback-continuation additive (identik eng test harness / pine v19-v20)."""
    n=len(c); rp=np.roll(R,1); rp[0]=R[0]; sig=np.zeros(n,bool)
    lvl=82.0 if side=='long' else 20.0
    q=(ap<=1.0)&(ap>=0.2)&(body>=0.3); ph=0; wu=-1; pk=0.0
    for i in range(1,n):
        intact=(c[i]>E[i]) if side=='long' else (c[i]<E[i])
        trig=((R[i]>lvl)and(rp[i]<=lvl)and intact) if side=='long' else ((R[i]<lvl)and(rp[i]>=lvl)and intact)
        if trig: ph=1; wu=i+W; pk=h[i] if side=='long' else l[i]; continue
        if ph>0:
            if i>wu or not intact: ph=0; continue
            if ph==1:
                if side=='long':
                    pk=max(pk,h[i])
                    if (pk-c[i])/pk*100>=1.0: ph=2
                else:
                    pk=min(pk,l[i])
                    if (c[i]-pk)/pk*100>=1.0: ph=2
            elif ph==2:
                if side=='long':
                    if c[i]>pk and c[i]>o[i] and q[i]: sig[i]=True; ph=0
                else:
                    if c[i]<pk and c[i]<o[i] and q[i]: sig[i]=True; ph=0
    return sig

def build_v20_context(df):
    """Hitung semua array sinyal v20 utk seluruh df (deterministik). Reuse eng.signals."""
    o=df['open'].to_numpy(float); h=df['high'].to_numpy(float)
    l=df['low'].to_numpy(float);  c=df['close'].to_numpy(float)
    cf=dict(DEF)
    R=rsi(c,cf['rsi_len']); E=ema(c,cf['ema_len']); A=atr(h,l,c,cf['atr_len'])
    ap=A/c*100.0; rng=h-l; body=np.where(rng>0,np.abs(c-o)/np.where(rng>0,rng,1),0.0)
    aL=pbsig(o,h,l,c,R,E,ap,body,'long'); aS=pbsig(o,h,l,c,R,E,ap,body,'short')
    cf['add_long']=aL; cf['add_short']=aS
    long_sig,short_sig,atr_pct,_=signals(df,cf,(o,h,l,c,R,E,A))
    tp=np.full(len(c),TP_BASE); tp[atr_pct>TP_WALL]=TP_GENTLE
    sl=np.full(len(c),SL_V20)*macro_sl_mult(df['dt'])   # ★ macro-SL widening (BTC-only, matches pine v20.1)
    return dict(o=o,h=h,l=l,c=c,A=A,long=long_sig,short=short_sig,tp=tp,sl=sl)

# per-ticker vol-normalized params (riset multiticker 26-Jun, [[btc-multiticker-eth-sol]]):
# BTC median ATR%15m 0.357 (baseline) / ETH 0.481 (1.35x) / SOL 0.699 (1.96x) -> param absolut BTC
# tak ter-vol-normalize kalau dipakai apa adanya di ETH/SOL (DD 2x lipat). Fix: scale modest per-ticker.
MULTI_PARAMS = {
 "BTCUSDT": dict(tp_base=2.0, tp_gentle=2.15, tp_wall=0.40, sl=1.9, ceil=1.0,  floor=0.20),
 "ETHUSDT": dict(tp_base=2.2, tp_gentle=2.35, tp_wall=0.54, sl=2.0, ceil=1.15, floor=0.27),
 "SOLUSDT": dict(tp_base=2.4, tp_gentle=2.55, tp_wall=0.78, sl=2.2, ceil=1.90, floor=0.39),
}
def build_v20_context_multi(df, sym):
    """Generalized build_v20_context, param per-symbol (MULTI_PARAMS). BTC path via
    build_v20_context() TETAP dipakai (0 regresi); ini KHUSUS ETH/SOL (juga jalan utk BTC kalau perlu)."""
    p=MULTI_PARAMS.get(sym, MULTI_PARAMS["BTCUSDT"])
    o=df['open'].to_numpy(float); h=df['high'].to_numpy(float)
    l=df['low'].to_numpy(float);  c=df['close'].to_numpy(float)
    cf=dict(DEF); cf['max_atr']=p['ceil']; cf['atr_floor']=p['floor']; cf['sl']=p['sl']
    R=rsi(c,cf['rsi_len']); E=ema(c,cf['ema_len']); A=atr(h,l,c,cf['atr_len'])
    ap=A/c*100.0; rng=h-l; body=np.where(rng>0,np.abs(c-o)/np.where(rng>0,rng,1),0.0)
    aL=pbsig(o,h,l,c,R,E,ap,body,'long'); aS=pbsig(o,h,l,c,R,E,ap,body,'short')
    cf['add_long']=aL; cf['add_short']=aS
    long_sig,short_sig,atr_pct,_=signals(df,cf,(o,h,l,c,R,E,A))
    tp=np.full(len(c),p['tp_base']); tp[atr_pct>p['tp_wall']]=p['tp_gentle']
    sl=np.full(len(c),p['sl'])
    return dict(o=o,h=h,l=l,c=c,A=A,long=long_sig,short=short_sig,tp=tp,sl=sl)

# ===================== STATE MACHINE v20 (faithful eng.py) =====================
def new_sleeve(): return dict(pos=0,entry=0.0,tp=0.0,sl=0.0,hi=0.0,lo=0.0,trail=None,
                              gap=0.0,pending=0,entry_i=-1,last_entry_i=-10**9,
                              last_exit_dir=0,last_exit_i=-10**9,
                              held=0,equity=1.0,ntr=0,nwin=0,loss_streak=0,hist=[])

def step_v20(s, i, ctx, fill_next_open=True, ai=None):
    """Proses bar i utk sleeve v20. Mengembalikan list event (string). Mutasi s in-place.
    `i`      = indeks dalam window/array ctx (utk akses harga/sinyal).
    `ai`     = indeks bar ABSOLUT (open_time//BAR_MS) utk bookkeeping cooldown lintas-run.
               None -> pakai i (mode selftest: i sudah absolut sepanjang CSV).
    FIX (28-Jun): cooldown dulu pakai i window-relatif yg KONSTAN tiap cron (i=len-1) ->
    bse selalu 0 -> re-entry searah terblok permanen. Kini pakai ai absolut."""
    aidx = i if ai is None else ai
    o,h,l,c,A=ctx['o'],ctx['h'],ctx['l'],ctx['c'],ctx['A']
    tp_a,sl_a=ctx['tp'],ctx['sl']; ev=[]
    fee=DEF['fee']; tact=DEF['trail_act']; tmult=DEF['trail_mult']; tmin=DEF['trail_min']; tmax=DEF['trail_max']
    # 1) isi pending di open[i]
    if s['pending']!=0 and s['pos']==0:
        s['entry']=o[i]; s['entry_i']=i; s['pos']=s['pending']
        tpct=tp_a[i-1]; spct=sl_a[i-1]
        if s['pos']>0: s['tp']=s['entry']*(1+tpct/100); s['sl']=s['entry']*(1-spct/100)
        else:          s['tp']=s['entry']*(1-tpct/100); s['sl']=s['entry']*(1+spct/100)
        s['gap']=max(tmin*s['entry']/100, min(tmax*s['entry']/100, A[i]*tmult))
        s['hi']=h[i]; s['lo']=l[i]; s['trail']=None; s['pending']=0
        ev.append(f"ENTRY v20 {'LONG' if s['pos']>0 else 'SHORT'} @ {s['entry']:.1f}  TP {s['tp']:.1f}  SL {s['sl']:.1f}")
    # 2) kelola exit di bar i (adverse-first; stop dari bar sebelumnya)
    if s['pos']!=0:
        if s['pos']>0:
            stop = s['sl'] if s['trail'] is None else max(s['sl'],s['trail'])
            ex=None; px=0.0
            if l[i]<=stop: px=min(o[i],stop) if o[i]<stop else stop; ex=('Trail' if (s['trail'] is not None and stop>s['sl']) else 'SL')
            elif h[i]>=s['tp']: px=max(o[i],s['tp']) if o[i]>s['tp'] else s['tp']; ex='TP'
            if ex:
                r=(px/s['entry']-1)-2*fee; s['equity']*=(1+LEVERAGE*r); s['ntr']+=1; s['nwin']+=int(r>0)
                s['loss_streak']=0 if r>0 else s.get('loss_streak',0)+1
                s.setdefault('hist',[]).append({"dir":1,"net":r}); s['hist']=s['hist'][-100:]
                ev.append(f"EXIT  v20 LONG  @ {px:.1f}  {ex}  ret {r*100:+.2f}%")
                s['pos']=0; s['last_exit_dir']=1; s['last_exit_i']=aidx
            else:
                s['hi']=max(s['hi'],h[i])
                if (s['hi']-s['entry'])>=tact*s['entry']/100:
                    nt=s['hi']-s['gap']; s['trail']=nt if s['trail'] is None else max(s['trail'],nt)
        else:
            stop = s['sl'] if s['trail'] is None else min(s['sl'],s['trail'])
            ex=None; px=0.0
            if h[i]>=stop: px=max(o[i],stop) if o[i]>stop else stop; ex=('Trail' if (s['trail'] is not None and stop<s['sl']) else 'SL')
            elif l[i]<=s['tp']: px=min(o[i],s['tp']) if o[i]<s['tp'] else s['tp']; ex='TP'
            if ex:
                r=(s['entry']/px-1)-2*fee; s['equity']*=(1+LEVERAGE*r); s['ntr']+=1; s['nwin']+=int(r>0)
                s['loss_streak']=0 if r>0 else s.get('loss_streak',0)+1
                s.setdefault('hist',[]).append({"dir":-1,"net":r}); s['hist']=s['hist'][-100:]
                ev.append(f"EXIT  v20 SHORT @ {px:.1f}  {ex}  ret {r*100:+.2f}%")
                s['pos']=0; s['last_exit_dir']=-1; s['last_exit_i']=aidx
            else:
                s['lo']=min(s['lo'],l[i])
                if (s['entry']-s['lo'])>=tact*s['entry']/100:
                    nt=s['lo']+s['gap']; s['trail']=nt if s['trail'] is None else min(s['trail'],nt)
    # 3) sinyal di close bar i -> pending utk bar berikut (cooldown, pakai indeks absolut)
    if s['pos']==0 and s['pending']==0:
        bse=aidx-s['last_exit_i']
        cdL=not(s['last_exit_dir']==1 and bse<COOLDOWN)
        cdS=not(s['last_exit_dir']==-1 and bse<COOLDOWN)
        if ctx['long'][i] and cdL: s['pending']=1
        elif ctx['short'][i] and cdS: s['pending']=-1
    return ev

# ===================== DATA LIVE =====================
FAPI="https://fapi.binance.com"
import urllib.parse as _uq
_HDR={"User-Agent":"Mozilla/5.0","Accept":"application/json"}
def bget(path, tries=3):
    """GET Binance fapi via rantai proxy (Binance ISP-block di ID). direct sekali (Proton/VPN on) ->
    3 proxy publik diulang `tries` kali dgn retry. Return JSON atau raise. Fix flap 'time gagal' single-proxy."""
    full=FAPI+path; enc=_uq.quote(full,safe="")
    chain=[(full,4)] + [                                     # direct cepat-fail (Proton) sekali
        ("https://proxy.cors.sh/"+full,15),                  # proxy1 cors.sh
        ("https://corsproxy.io/?url="+enc,15),               # proxy2 corsproxy.io
        ("https://api.allorigins.win/raw?url="+enc,20),      # proxy3 allorigins
    ]*max(1,tries)                                           # proxy diulang -> tahan flap
    last=""
    for url,to in chain:
        try:
            r=SESS.get(url, timeout=to, verify=VERIFY, headers=_HDR)
            if r.status_code>=400: last=f"http{r.status_code}@{url[:24]}"; continue
            j=r.json()
            if j not in (None,{},[]): return j
            last="empty@"+url[:24]
        except Exception as e: last=f"{type(e).__name__}@{url[:24]}"
    raise RuntimeError(f"binance gagal semua proxy ({last})")

def fetch_klines(limit=1000):
    """Ambil klines 15m TERTUTUP (buang bar berjalan). Return None kalau gagal (jangan crash)."""
    try:
        b=bget(f"/fapi/v1/klines?symbol={SYMBOL}&interval={INTERVAL}&limit={limit}")
        now=int(time.time()*1000)   # jam lokal cukup buat filter bar-tertutup; hemat 1 call + hilangkan flap serverTime
    except Exception as e:
        print("  fetch_klines gagal:", str(e)[:120]); return None
    if not b or not isinstance(b,list): return None
    if b[-1][6] > now: b=b[:-1]   # close_time>now => bar belum tutup
    if not b: return None
    df=pd.DataFrame(b,columns=["open_time","open","high","low","close","volume","close_time","qav","trades","tbbav","tbqav","ig"])
    for col in ["open","high","low","close"]: df[col]=df[col].astype(float)
    df["dt"]=pd.to_datetime(df["open_time"],unit="ms",utc=True)
    return df[["open_time","dt","open","high","low","close"]]

# ===================== STATE I/O =====================
def load_state():
    if os.path.exists(STATE_F):
        try:
            with open(STATE_F) as fp: return json.load(fp)
        except Exception as e:
            try: os.replace(STATE_F, STATE_F+".corrupt")
            except Exception: pass
            print(f"  ⚠️ state korup ({str(e)[:60]}) -> backup .corrupt, mulai fresh")
    return dict(v20=new_sleeve(),last_open_time=0)
def save_state(st):
    tmp=STATE_F+".tmp"                                       # atomic write
    with open(tmp,"w") as fp: json.dump(st,fp,indent=1)
    os.replace(tmp, STATE_F)

def alert(events):
    for e in events:
        print("  >>", e)
        (log_err if any(t in e for t in ("GAGAL","❌","MISMATCH","BREAKER","gagal","error")) else log_run)(e)
    if events:
        try:
            from notify_wa import send_whatsapp
            send_whatsapp("🤖 BTC bot\n" + "\n".join(events))
        except Exception as ex: print("  WA gagal:",ex)
    if WEBHOOK and events:
        try: SESS.post(WEBHOOK,json={"bot":"v20","events":events,"ts":int(time.time())},timeout=10,verify=VERIFY)
        except Exception as ex: print("  webhook gagal:",ex)

import json as _json
CONFIG_F = os.path.join(HERE, "bot_config.json")
def load_config():
    """Baca config live-adjustable (size/leverage/live) dari bot_config.json (diatur via admin)."""
    try:
        with open(CONFIG_F) as f: return _json.load(f)
    except Exception: return {"live":False,"net":"testnet","size_usd":120,"leverage":1,"symbol":"BTC/USDT:USDT","sleeves":{"v20":True}}

def set_config(**kw):
    """Update field bot_config.json (atomic). Dipakai circuit-breaker utk matikan live."""
    try:
        with open(CONFIG_F) as f: c=_json.load(f)
    except Exception: c={}
    c.update(kw)
    tmp=CONFIG_F+".tmp"
    with open(tmp,"w") as f: _json.dump(c,f,indent=2)
    os.replace(tmp, CONFIG_F); return c

def check_breaker(st, cfg):
    """CIRCUIT-BREAKER: halt kalau drawdown dari puncak >= max_dd_pct ATAU loss beruntun >= max_loss_streak.
    Cuma TRIP saat live=true (lindungi uang asli). Track peak di st['breaker']. Return {tripped,reason,dd,streak}."""
    sl=st['v20']
    b=st.setdefault('breaker', {"peak":sl['equity'],"halted":False,"reason":""})
    b['peak']=max(b.get('peak',sl['equity']), sl['equity'])
    dd=(b['peak']-sl['equity'])/b['peak']*100 if b['peak']>0 else 0.0
    streak=int(sl.get('loss_streak',0))
    if cfg.get('live') and cfg.get('net') in ("mainnet","testnet"):   # M8: live -> DD dari equity NYATA (wallet+unrealized)
        try:
            _bal=_exchange(cfg.get('net')).fetch_balance()
            eq=float(_bal.get('info',{}).get('totalMarginBalance') or (_bal.get('total',{}) or {}).get('USDT') or 0)
            if eq>0:
                rp=max(float(b.get('real_peak',eq)), eq); b['real_peak']=rp
                dd=(rp-eq)/rp*100 if rp>0 else 0.0
        except Exception: pass
    bc=cfg.get('breaker',{}) or {}
    if not bc.get('enabled',True): return {"tripped":False,"reason":"","dd":dd,"streak":streak}
    max_dd=float(bc.get('max_dd_pct',15)); max_streak=int(bc.get('max_loss_streak',6))
    reasons=[]
    if dd>=max_dd: reasons.append(f"DD {dd:.1f}% ≥ {max_dd:.0f}%")
    if streak>=max_streak: reasons.append(f"{streak}x loss beruntun ≥ {max_streak}")
    tripped = bool(reasons) and not b.get('halted') and bool(cfg.get('live',False))
    return {"tripped":tripped,"reason":" ; ".join(reasons),"dd":dd,"streak":streak}

# STATISTICAL TRIPWIRE (2-Jul): pre-committed alarm floors dari distribusi rolling
# 2019-2025 sendiri (bukan operasi sinyal) -- lihat CLAUDE.md utk derivasi lengkap.
# wr41/ret41 = rolling 41-trade window (semua arah); wr30_short = rolling 30-trade
# window KHUSUS short (short historically lebih lemah dari long). dd_ceiling = dari
# check_breaker's dd-dari-puncak (closed equity), bukan dihitung ulang di sini.
TRIPWIRE = dict(wr41_floor=46.3, ret41_floor=-4.7, wr30_short_floor=46.7, dd_ceiling=11.1)

def check_tripwire(st, cfg, breaker_dd=0.0):
    """2-tier escalation: 1 metrik breach floor historis -> size dipotong 50% (tier1);
    >=2 metrik breach BARENGAN -> pause total (tier2, sama efeknya dgn circuit-breaker
    DD/streak). Rasional 2-tier: 1 metrik nyimpang bisa noise biasa (tiap metrik individual
    MEMANG pernah tembus floornya sendiri di histori 6-tahun -- itu definisi floor), tapi
    >=2 metrik SEKALIGUS di luar apapun yg pernah kejadian bareng secara historis = sinyal
    kuat ada yg berubah (regime shift/bug), bukan varians normal -- circuit-breaker DD/streak
    yang sudah ada baru trip di 15%/6x-beruntun (jauh lebih longgar), tripwire ini nangkep
    anomali lebih dini via bentuk distribusi, bukan cuma titik ekstrem.
    Butuh histori trade cukup (>=41 utk wr41/ret41, >=30 short utk wr30_short) -- sebelum itu,
    metrik terkait di-skip (bukan auto-tripped kosongan)."""
    sl=st['v20']; hist=sl.get('hist',[])
    tw=st.setdefault('tripwire', {"tier":0,"reasons":[],"size_mult":1.0})
    tc=cfg.get('tripwire',{}) or {}
    if not tc.get('enabled',True):
        tw.update(tier=0,reasons=[],size_mult=1.0); return tw
    reasons=[]
    if len(hist)>=41:
        last41=hist[-41:]
        wr41=sum(1 for x in last41 if x['net']>0)/41*100
        eq=1.0
        for x in last41: eq*=(1+x['net'])
        ret41=(eq-1)*100
        if wr41<TRIPWIRE['wr41_floor']: reasons.append(f"WR-41 {wr41:.1f}% < floor {TRIPWIRE['wr41_floor']}%")
        if ret41<TRIPWIRE['ret41_floor']: reasons.append(f"Return-41 {ret41:.1f}% < floor {TRIPWIRE['ret41_floor']}%")
    shorts=[x for x in hist if x['dir']<0]
    if len(shorts)>=30:
        last30s=shorts[-30:]
        wr30s=sum(1 for x in last30s if x['net']>0)/30*100
        if wr30s<TRIPWIRE['wr30_short_floor']: reasons.append(f"WR-30-short {wr30s:.1f}% < floor {TRIPWIRE['wr30_short_floor']}%")
    if breaker_dd>TRIPWIRE['dd_ceiling']: reasons.append(f"DD {breaker_dd:.1f}% > ceiling {TRIPWIRE['dd_ceiling']}%")
    tier = 2 if len(reasons)>=2 else (1 if len(reasons)==1 else 0)
    tw['tier']=tier; tw['reasons']=reasons; tw['size_mult']=(0.5 if tier==1 else 1.0)
    return tw

SECRETS_F = os.path.join(HERE, "bot_secrets.json")
def load_keys(net="mainnet"):
    """API key per-net dari bot_secrets.json. Format baru:
    {"mainnet":{"key","secret"}, "testnet":{"key","secret"}}. Backward-compat flat = mainnet.
    Fallback env: BINANCE_KEY/SECRET (mainnet), BINANCE_TESTNET_KEY/SECRET (testnet)."""
    try:
        s=_json.load(open(SECRETS_F))
        if isinstance(s.get(net),dict): return s[net].get("key",""), s[net].get("secret","")
        if "key" in s and net=="mainnet": return s.get("key",""), s.get("secret","")   # format lama = mainnet
    except Exception: pass
    if net=="testnet": return os.environ.get("BINANCE_TESTNET_KEY",""), os.environ.get("BINANCE_TESTNET_SECRET","")
    return os.environ.get("BINANCE_KEY",""), os.environ.get("BINANCE_SECRET","")
_EX = None
def _exchange(net="mainnet"):
    global _EX
    if net not in ("mainnet","testnet"):           # M6 fail-CLOSED: net aneh -> refuse (jangan diam2 ke live)
        raise RuntimeError(f"net invalid '{net}' (harus mainnet/testnet) — refuse")
    k,s=load_keys(net)
    import ccxt
    ex = ccxt.binanceusdm({"apiKey":k,"secret":s,"enableRateLimit":True,"options":{"defaultType":"future"}})
    ex.has['fetchCurrencies']=False                # skip sapi spot call (testnet ga punya sapi; bot futures-only)
    if net=="mainnet":                             # mainnet ke-block SNI-DPI ISP -> lewat proxy lokal anti-DPI (TANPA VPN). testnet ga perlu.
        px=os.environ.get("BINANCE_PROXY","socks5h://127.0.0.1:1080")
        if px:
            try: ex.socksProxy=px
            except Exception: ex.proxies={"http":px,"https":px}
    if net!="mainnet":   # ccxt sudah DROP set_sandbox_mode utk binance futures -> override URL ke testnet manual
        api=ex.urls.get('api',{})
        if isinstance(api,dict):
            for kk,vv in list(api.items()):
                if isinstance(vv,str): api[kk]=vv.replace('fapi.binance.com','testnet.binancefuture.com')
    try: ex.set_position_mode(False)               # M5: PAKSA one-way (tolak hedge mis-reconcile)
    except Exception: pass
    _EX = ex; return ex

def read_position(ex, sym):
    """Posisi BTC bertanda DARI EXCHANGE = sumber kebenaran. SUM semua leg (hedge-safe, M5).
    RAISE kalau tak bisa dipastikan (jangan anggap 0=flat saat baca gagal -> cegah stack posisi M2)."""
    poss = ex.fetch_positions([sym])
    if not poss: return 0.0   # ccxt: [] = FLAT (posisi entryPrice 0 di-filter). Gagal-fetch ASLI = THROW exception (bukan []) -> ketangkap try sync_live. (M2: jangan raise di sini -> dulu blokir SEMUA open)
    tot=0.0; seen=False
    for p in poss:
        info = p.get('info',{}) or {}
        if 'positionAmt' in info:
            try: tot+=float(info['positionAmt']); seen=True; continue
            except Exception: pass
        amt = p.get('contracts'); side = p.get('side')
        if amt is not None and side:
            tot += (float(amt) if side=='long' else -float(amt)); seen=True
    if not seen: raise RuntimeError("posisi tak ter-parse — refuse (jangan order)")
    return tot

def _sgn(x, eps=1e-9): return 1 if x>eps else (-1 if x<-eps else 0)

def sync_live(label, desired_sign, price):
    """REKONSILIASI: dorong posisi exchange -> desired_sign (-1/0/+1).
    Fix4: (1) timing — dipanggil dgn desired = pos/pending sehingga entry dieksekusi di run
    yg SAMA dgn sinyal (≈ next-open, bukan telat 1 bar). (2) qty — close pakai qty AKTUAL
    dari exchange, bukan hitung-ulang. (3) rekonsiliasi — baca posisi nyata tiap run (truth).
    (4) konfirmasi — re-baca posisi setelah order, alert kalau mismatch.
    live=false -> log saja (paper, NOL order). Error -> pesan utk WA, tak pernah raise."""
    cfg = load_config()
    sym = cfg.get("symbol","BTC/USDT:USDT")
    lev = max(1, min(1, int(cfg.get("leverage",1))))       # M3: clamp <=1x DI EKSEKUSI (config = untrusted)
    size_usd = min(float(cfg.get("size_usd",120)), float(cfg.get("max_size_usd",2000)))   # M3: cap notional
    size_usd *= float(cfg.get("tripwire_size_mult",1.0))    # tripwire tier1: potong 50% otomatis (check_tripwire)
    net = cfg.get("net","testnet")                         # switch 2: testnet (default aman) / mainnet
    tag = "MAINNET" if net=="mainnet" else "TESTNET"
    tgt_qty = round(size_usd*lev/price, 3)                 # BTC presisi 0.001
    if not cfg.get("live", False):
        # PAPER tapi fill PURA-PURA nabrak ORDERBOOK ASLI mainnet (no order, no uang). Cuma saat BERUBAH.
        import paper_ob, json as _j, time as _t
        led=os.path.join(HERE,"paper_ob_state.json")
        try:
            with open(led) as _lf: L=_j.load(_lf)
        except Exception: L={"fills":[],"last_sign":0}
        if desired_sign==L.get("last_sign",0):
            print(f"  [PAPER-OB] {label}: hold sign {desired_sign}"); return None
        msg=f"  [PAPER] {label}: target FLAT"
        if desired_sign!=0:
            try:
                f=paper_ob.orderbook_fill("buy" if desired_sign>0 else "sell", tgt_qty)
                L["fills"].append(dict(ts=int(_t.time()),label=label,sign=desired_sign,**f))
                msg=(f"📝 PAPER-OB {('LONG' if desired_sign>0 else 'SHORT')} {tgt_qty} BTC @ ~{f['avg_px']:.1f} "
                     f"slip {f['slip_pct']:+.3f}% ({f['levels_used']}lvl, {'fill OK' if f['filled'] else 'DEPTH HABIS'})")
            except Exception as e: msg=f"  [PAPER] {label}: target {desired_sign} | OB-sim gagal {str(e)[:40]}"
        L["last_sign"]=desired_sign; L["fills"]=L["fills"][-200:]
        _tmp=led+".tmp"                                     # M9: tulis atomik (cegah korup -> last_sign reset -> dup fill)
        with open(_tmp,"w") as _wf: _j.dump(L,_wf,indent=1)
        os.replace(_tmp, led)
        print("  "+msg); return msg
    k,sec = load_keys(net)
    if not k or not sec: return f"⚠️ {label}: API key {tag} belum diisi"
    if desired_sign!=0 and (tgt_qty*price < 100 or tgt_qty < 0.001):
        msg=f"⚠️ {label}: target ${tgt_qty*price:.0f} < min Binance $100 — skip"; print("  "+msg); return msg
    try:
        ex=_exchange(net)
        try: ex.set_leverage(lev, sym)
        except Exception: pass
        _bk=int(time.time()//900)                          # M1 defense: clientOrderId deterministik per-bucket-15m
        def _cid(a): return (f"{label}-{_bk}-{a}")[:36]    # 2 run konkuren -> cid SAMA -> Binance TOLAK order dobel (exchange-side dedup)
        actual = read_position(ex, sym)                    # signed BTC = TRUTH
        asign = _sgn(actual)
        tol = max(0.0005, 0.02*tgt_qty)                     # ~setengah-lot: posisi ter-kuantisasi 0.001 harus benar2 cocok
        if asign==desired_sign and (desired_sign==0 or abs(abs(actual)-tgt_qty)<=tol):
            return None                                    # sudah sinkron, no-op
        orders=[]
        # 1) tutup/flip: kalau ada posisi arah-salah, close qty AKTUAL (reduceOnly)
        if asign!=0 and asign!=desired_sign:
            q=abs(round(actual,3))
            ex.create_order(sym,"market","sell" if actual>0 else "buy", q, params={"reduceOnly":True,"newClientOrderId":_cid("close")})
            orders.append(f"close {actual:+.3f}"); actual=0.0; asign=0
        # 2) buka/sesuaikan menuju desired
        if desired_sign!=0:
            need=round(desired_sign*tgt_qty-actual, 3)     # delta bertanda
            if abs(need)>=0.001:
                ex.create_order(sym,"market","buy" if need>0 else "sell", abs(need), params={"newClientOrderId":_cid("open")})
                orders.append(f"open {need:+.3f}")
        elif asign!=0:                                      # desired flat tapi masih nyangkut
            q=abs(round(actual,3))
            ex.create_order(sym,"market","sell" if actual>0 else "buy", q, params={"reduceOnly":True,"newClientOrderId":_cid("flat")})
            orders.append(f"flat {actual:+.3f}")
        # 3) konfirmasi: re-baca posisi
        conf=read_position(ex,sym); csign=_sgn(conf)
        ok=(csign==desired_sign) and (desired_sign==0 or abs(abs(conf)-tgt_qty)<=tol)
        msg=f"{'✅' if ok else '⚠️'} {tag} {label} -> sign {desired_sign} ({' / '.join(orders) or 'noop'}); pos {conf:+.3f}"
        if not ok: msg+=" — MISMATCH, cek manual!"
        try:
            from notify_wa import send_whatsapp; send_whatsapp("💰 "+msg)
        except Exception: pass
        print("  "+msg); return msg
    except Exception as e:
        msg=f"❌ {tag} {label} sync GAGAL: {str(e)[:120]}"; print("  "+msg); return msg

# ===================== AKSI =====================
def do_once():
    st=load_state()
    df=fetch_klines(1000)
    if df is None: print("fetch gagal, skip bar ini."); return
    if len(df) < DEF['warmup']+10: print("data kurang utk warmup"); return
    ot=df["open_time"].to_numpy(); n=len(df)
    last_ot=int(ot[-1]); prev_done=int(st.get("last_open_time",0))
    if last_ot==prev_done:
        print(f"bar {df['dt'].iloc[-1]} sudah diproses, skip."); return
    ctx=build_v20_context(df)
    # tentukan bar yg belum diproses (backfill kalau cron sempat terlewat)
    if prev_done>0:
        idx=int(np.searchsorted(ot, prev_done))
        start = idx+1 if (idx<n and ot[idx]==prev_done) else (n-1)
    else:
        start = n-1
    start=max(start, DEF['warmup'])
    ev=[]
    for i in range(start, n):
        ev+=step_v20(st['v20'], i, ctx, ai=int(ot[i])//BAR_MS)
    price=ctx['c'][n-1]
    print(f"== bar {df['dt'].iloc[-1]} close {price:.1f} | proses {n-start} bar (start idx {start}) ==")
    cfg=load_config()
    if cfg.get('sleeves',{}).get('v20',True):
        sl=st['v20']
        desired = sl['pos'] if sl['pos']!=0 else sl['pending']   # collapse pending -> entry same-run (fix timing)
        msg=sync_live("v20", desired, price)
        if msg: ev.append(msg)
    if ev: alert(ev)
    else:  print("  (tidak ada aksi bar ini)")
    st["last_open_time"]=last_ot; save_state(st); show_status(st, price=price)

def show_status(st=None, price=None):
    if st is None: st=load_state()
    print("\n----- STATUS v20 (paper) -----")
    sl=st['v20']; ps={0:'FLAT',1:'LONG',-1:'SHORT'}[sl['pos']]
    wr=(sl['nwin']/sl['ntr']*100) if sl['ntr'] else 0
    line=f"  v20: {ps:5s}"
    if sl['pos']!=0: line+=f" entry {sl['entry']:.1f} TP {sl['tp']:.1f} SL {sl['sl']:.1f}"
    line+=f"  | equity x{sl['equity']:.3f}  trades {sl['ntr']} WR {wr:.0f}%"
    print(line)
    print(f"  modal ${CAPITAL:.0f} -> ${CAPITAL*sl['equity']:.0f}")

def selftest():
    """Replay CSV lokal lewat state-machine bot; bandingkan vs eng.py (buktikan faithful)."""
    print("== SELFTEST: replay btc_15m_full.csv lewat logika BOT (v20-only) ==")
    df=pd.read_csv(os.path.join(HERE,"btc_15m_full.csv"),parse_dates=['dt'])
    ctx=build_v20_context(df); n=len(df)
    sv=new_sleeve(); start=max(DEF['warmup'],DEF['ema_len']+2)
    for i in range(start,n):
        step_v20(sv,i,ctx)   # ai=None -> i absolut sepanjang CSV
    print(f"  BOT v20 sleeve : ret {(sv['equity']-1)*100:+.0f}%  trades {sv['ntr']}  WR {sv['nwin']/sv['ntr']*100:.1f}%")
    # banding eng.py utk v20 (rebuild add-signals utk ref)
    o=df['open'].to_numpy(float);h=df['high'].to_numpy(float);l=df['low'].to_numpy(float);c=df['close'].to_numpy(float)
    R=rsi(c,DEF['rsi_len']);E=ema(c,DEF['ema_len']);A=atr(h,l,c,DEF['atr_len']);ap=A/c*100;rng=h-l
    body=np.where(rng>0,np.abs(c-o)/np.where(rng>0,rng,1),0.0)
    aL=pbsig(o,h,l,c,R,E,ap,body,'long'); aS=pbsig(o,h,l,c,R,E,ap,body,'short')
    er,et=eng_run(df,{'add_long':aL,'add_short':aS,'tp':ctx['tp'],'sl':ctx['sl']})
    print(f"  ENG v20 (ref)  : ret {er['ret']:+.0f}%  trades {er['n']}  WR {er['wr']:.1f}%   <- bot harus ~sama")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--once",action="store_true",help="proses bar terbaru (cron)")
    ap.add_argument("--status",action="store_true",help="tampilkan status posisi/equity")
    ap.add_argument("--selftest",action="store_true",help="replay CSV, buktikan bot==backtest")
    ap.add_argument("--reset",action="store_true",help="reset state paper")
    a=ap.parse_args()
    if a.reset: save_state(dict(v20=new_sleeve(),last_open_time=0)); print("state direset.")
    elif a.selftest: selftest()
    elif a.status: show_status()
    elif a.once:
        lk=acquire_lock()
        if lk is None: print("⏭️ run lain masih jalan -> skip (cegah double-order)")
        else:
            try: do_once()
            finally: release_lock(lk)
    else: ap.print_help()
