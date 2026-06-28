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
# v20 exit (sama dgn version20 pine / DEF)
TP_BASE, TP_GENTLE, TP_WALL, SL_V20 = 2.0, 2.15, 0.40, 1.9
COOLDOWN = 6
PB_W = 28
SESS = requests.Session()

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
    sl=np.full(len(c),SL_V20)
    return dict(o=o,h=h,l=l,c=c,A=A,long=long_sig,short=short_sig,tp=tp,sl=sl)

# ===================== STATE MACHINE v20 (faithful eng.py) =====================
def new_sleeve(): return dict(pos=0,entry=0.0,tp=0.0,sl=0.0,hi=0.0,lo=0.0,trail=None,
                              gap=0.0,pending=0,entry_i=-1,last_entry_i=-10**9,
                              last_exit_dir=0,last_exit_i=-10**9,
                              held=0,equity=1.0,ntr=0,nwin=0)

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
def fetch_klines(limit=1000):
    """Ambil klines 15m TERTUTUP (buang bar berjalan). Return None kalau gagal (jangan crash)."""
    try:
        r=SESS.get("https://fapi.binance.com/fapi/v1/klines",
                   params={"symbol":SYMBOL,"interval":INTERVAL,"limit":limit},timeout=25,verify=VERIFY)
        r.raise_for_status(); b=r.json()
        now=SESS.get("https://fapi.binance.com/fapi/v1/time",timeout=15,verify=VERIFY).json()["serverTime"]
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
    for e in events: print("  >>", e)
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
    except Exception: return {"live":False,"size_usd":120,"leverage":1,"symbol":"BTC/USDT:USDT","sleeves":{"v20":True}}

SECRETS_F = os.path.join(HERE, "bot_secrets.json")
def load_keys():
    """API key dari bot_secrets.json (diisi via dashboard) -> fallback env var."""
    try:
        s=_json.load(open(SECRETS_F)); return s.get("key",""), s.get("secret","")
    except Exception:
        return os.environ.get("BINANCE_KEY",""), os.environ.get("BINANCE_SECRET","")
_EX = None
def _exchange():
    global _EX
    k,s=load_keys()
    import ccxt
    _EX = ccxt.binanceusdm({"apiKey":k,"secret":s,"enableRateLimit":True,"options":{"defaultType":"future"}})
    return _EX

def read_position(ex, sym):
    """Posisi BTC bertanda (long +, short -, 0 flat) DARI EXCHANGE = sumber kebenaran.
    Pakai info.positionAmt (Binance, signed) lalu fallback contracts/side (ccxt unified)."""
    poss = ex.fetch_positions([sym])
    for p in poss:
        info = p.get('info',{}) or {}
        if 'positionAmt' in info:
            try: return float(info['positionAmt'])
            except Exception: pass
        amt = p.get('contracts'); side = p.get('side')
        if amt and side:
            return float(amt) if side=='long' else -float(amt)
    return 0.0

def _sgn(x, eps=1e-9): return 1 if x>eps else (-1 if x<-eps else 0)

def sync_live(label, desired_sign, price):
    """REKONSILIASI: dorong posisi exchange -> desired_sign (-1/0/+1).
    Fix4: (1) timing — dipanggil dgn desired = pos/pending sehingga entry dieksekusi di run
    yg SAMA dgn sinyal (≈ next-open, bukan telat 1 bar). (2) qty — close pakai qty AKTUAL
    dari exchange, bukan hitung-ulang. (3) rekonsiliasi — baca posisi nyata tiap run (truth).
    (4) konfirmasi — re-baca posisi setelah order, alert kalau mismatch.
    live=false -> log saja (paper, NOL order). Error -> pesan utk WA, tak pernah raise."""
    cfg = load_config()
    sym = cfg.get("symbol","BTC/USDT:USDT"); lev = int(cfg.get("leverage",1))
    size_usd = float(cfg.get("size_usd",120))
    tgt_qty = round(size_usd*lev/price, 3)                 # BTC presisi 0.001
    if not cfg.get("live", False):
        print(f"  [PAPER] {label}: target sign {desired_sign} (~{tgt_qty} BTC)"); return None
    k,sec = load_keys()
    if not k or not sec: return f"⚠️ {label}: API key belum diisi"
    if desired_sign!=0 and (tgt_qty*price < 100 or tgt_qty < 0.001):
        msg=f"⚠️ {label}: target ${tgt_qty*price:.0f} < min Binance $100 — skip"; print("  "+msg); return msg
    try:
        ex=_exchange()
        try: ex.set_leverage(lev, sym)
        except Exception: pass
        actual = read_position(ex, sym)                    # signed BTC = TRUTH
        asign = _sgn(actual)
        tol = max(0.0005, 0.02*tgt_qty)                     # ~setengah-lot: posisi ter-kuantisasi 0.001 harus benar2 cocok
        if asign==desired_sign and (desired_sign==0 or abs(abs(actual)-tgt_qty)<=tol):
            return None                                    # sudah sinkron, no-op
        orders=[]
        # 1) tutup/flip: kalau ada posisi arah-salah, close qty AKTUAL (reduceOnly)
        if asign!=0 and asign!=desired_sign:
            q=abs(round(actual,3))
            ex.create_order(sym,"market","sell" if actual>0 else "buy", q, params={"reduceOnly":True})
            orders.append(f"close {actual:+.3f}"); actual=0.0; asign=0
        # 2) buka/sesuaikan menuju desired
        if desired_sign!=0:
            need=round(desired_sign*tgt_qty-actual, 3)     # delta bertanda
            if abs(need)>=0.001:
                ex.create_order(sym,"market","buy" if need>0 else "sell", abs(need))
                orders.append(f"open {need:+.3f}")
        elif asign!=0:                                      # desired flat tapi masih nyangkut
            q=abs(round(actual,3))
            ex.create_order(sym,"market","sell" if actual>0 else "buy", q, params={"reduceOnly":True})
            orders.append(f"flat {actual:+.3f}")
        # 3) konfirmasi: re-baca posisi
        conf=read_position(ex,sym); csign=_sgn(conf)
        ok=(csign==desired_sign) and (desired_sign==0 or abs(abs(conf)-tgt_qty)<=tol)
        msg=f"{'✅' if ok else '⚠️'} LIVE {label} -> sign {desired_sign} ({' / '.join(orders) or 'noop'}); pos {conf:+.3f}"
        if not ok: msg+=" — MISMATCH, cek manual!"
        try:
            from notify_wa import send_whatsapp; send_whatsapp("💰 "+msg)
        except Exception: pass
        print("  "+msg); return msg
    except Exception as e:
        msg=f"❌ {label} sync GAGAL: {str(e)[:120]}"; print("  "+msg); return msg

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
    elif a.once: do_once()
    else: ap.print_help()
