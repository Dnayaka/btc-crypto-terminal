#!/usr/bin/env python3
"""bot_v22.py — bot auto-trade BTC v20-ONLY (momentum RSI-breakout + pullback + regime-TP).

Sleeve funding & CVD DIHAPUS (28-Jun, permintaan user). Dulu 3-sleeve (70/15/15); kini
murni v20 (alokasi 100%). Logika v20 di-IMPOR dari bot_v20_funding.py (tervalidasi,
zero-drift). File ini = RUNNER cron yg dipakai (run_bot.sh -> bot_v22.py --once), nulis
state ke bot_v22_state.json yg dibaca dashboard admin/terminal.

PEMAKAIAN:
  python3 bot_v22.py --selftest    # replay CSV, buktikan v20 == backtest tervalidasi
  python3 bot_v22.py --status      # posisi & equity v20
  python3 bot_v22.py --once        # proses bar terbaru (cron 15m, backfill bar terlewat)

DRY-RUN default (cuma sinyal). Live diatur via bot_config.json (admin localhost:8789).
Leverage <=1x.
"""
import os, json, argparse
import numpy as np, pandas as pd
from eng import DEF
from bot_v20_funding import (build_v20_context, step_v20, new_sleeve, fetch_klines,
                             alert, load_config, sync_live, BAR_MS, check_breaker, check_tripwire,
                             set_config, log_run, log_err)

HERE    = "/home/dnayaka/Documents/dynamic_rsi/btc-terminal"
CAPITAL = float(os.environ.get("BOT_CAPITAL", 1000.0))
STATE_F = os.path.join(HERE, "bot_v22_state.json")

# ---------- state ----------
def load_state():
    if os.path.exists(STATE_F):
        try:
            with open(STATE_F) as f: return json.load(f)
        except Exception as e:
            try: os.replace(STATE_F, STATE_F+".corrupt")   # simpan utk forensik
            except Exception: pass
            print(f"  ⚠️ state korup ({str(e)[:60]}) -> backup .corrupt, mulai fresh")
    return dict(v20=new_sleeve(), last_open_time=0)
def save_state(st):
    tmp=STATE_F+".tmp"                                       # tulis-lalu-rename = atomic
    with open(tmp,"w") as f: json.dump(st,f,indent=1)
    os.replace(tmp, STATE_F)

def show_status(st=None):
    if st is None: st=load_state()
    sl=st['v20']; ps={0:'FLAT',1:'LONG',-1:'SHORT'}[sl['pos']]
    wr=(sl['nwin']/sl['ntr']*100) if sl['ntr'] else 0
    print("\n----- STATUS v20 (paper) -----")
    line=f"  v20: {ps:5s}"
    if sl['pos']!=0: line+=f" entry {sl['entry']:.1f} TP {sl['tp']:.1f} SL {sl['sl']:.1f}"
    line+=f"  | equity x{sl['equity']:.3f} trades {sl['ntr']} WR {wr:.0f}%"
    print(line)
    print(f"  modal ${CAPITAL:.0f} -> ${CAPITAL*sl['equity']:.0f}")

# ---------- aksi ----------
def do_once():
    st=load_state()
    df=fetch_klines(1000)   # 1000 bar: EMA200 konvergen penuh (div vs full-history ~0.0003%) + backfill lebih dalam
    if df is None: print("fetch gagal, skip bar ini."); log_err("fetch_klines gagal — skip bar"); return
    if len(df) < DEF['warmup']+10: print("data kurang"); log_err("data kurang utk warmup"); return
    ot=df["open_time"].to_numpy(); n=len(df)
    last_ot=int(ot[-1]); prev_done=int(st.get("last_open_time",0))
    if last_ot==prev_done:
        print(f"bar {df['dt'].iloc[-1]} sudah diproses, skip."); return
    ctx=build_v20_context(df)
    # backfill: proses semua bar yg belum diproses (tahan kalau cron sempat terlewat)
    if prev_done>0:
        idx=int(np.searchsorted(ot, prev_done))
        start = idx+1 if (idx<n and ot[idx]==prev_done) else (n-1)
    else:
        start = n-1
    start=max(start, DEF['warmup'])
    price=ctx['c'][n-1]
    ev=[]
    for i in range(start, n):
        ev+=step_v20(st['v20'], i, ctx, ai=int(ot[i])//BAR_MS)
    print(f"== bar {df['dt'].iloc[-1]} close {price:.1f} | proses {n-start} bar (start idx {start}) ==")
    sl0=st['v20']; log_run(f"bar {df['dt'].iloc[-1]} close {price:.1f} | pos {({0:'FLAT',1:'LONG',-1:'SHORT'}[sl0['pos']])} eq x{sl0['equity']:.3f} | proses {n-start} bar")
    cfg=load_config(); sl=st['v20']
    # CIRCUIT-BREAKER: cek SEBELUM eksekusi. Kalau trip -> flat posisi (live masih on) lalu matikan live.
    br=check_breaker(st, cfg)
    if br['tripped']:
        hflat=sync_live("v20-HALT", 0, price)                # tutup posisi mumpung live masih on
        st['breaker']['halted']=True; st['breaker']['reason']=br['reason']
        set_config(live=False, halted=True, halt_reason=br['reason'])
        hmsg=f"🛑 CIRCUIT BREAKER: {br['reason']} — LIVE OFF, posisi diflat. Resume: bot_v22.py --resume"
        ev.append(hmsg)
        if hflat: ev.append("   flatten: "+hflat)             # hasil/error penutupan posisi
        try:
            from notify_wa import send_whatsapp; send_whatsapp("🛑 "+hmsg)
        except Exception: pass
    else:
        # STATISTICAL TRIPWIRE: cek SETELAH circuit-breaker (breaker = titik-ekstrem tunggal,
        # tripwire = bentuk-distribusi -- 2 metrik nyimpang bareng = anomali lebih dini).
        tw=check_tripwire(st, cfg, breaker_dd=br['dd'])
        if tw['tier']>=2:
            # >=2 metrik nyimpang bareng -> pause (skip eksekusi run ini, walau paper --
            # biar observasi paper meaningful: "kalau ini live, di sini bakal berhenti").
            already_halted = st.get('breaker',{}).get('halted')
            if cfg.get('live',False) and not already_halted:
                hflat=sync_live("v20-TRIPWIRE-HALT", 0, price)
                st.setdefault('breaker',{})['halted']=True
                st['breaker']['reason']="TRIPWIRE: "+" ; ".join(tw['reasons'])
                set_config(live=False, halted=True, halt_reason=st['breaker']['reason'], tripwire_size_mult=1.0)
                hmsg=f"🛑 TRIPWIRE PAUSE ({len(tw['reasons'])} metrik breach bareng): {' ; '.join(tw['reasons'])} — LIVE OFF. Resume: bot_v22.py --resume"
                ev.append(hmsg)
                if hflat: ev.append("   flatten: "+hflat)
                try:
                    from notify_wa import send_whatsapp; send_whatsapp("🛑 "+hmsg)
                except Exception: pass
            else:
                ev.append(f"ℹ️ TRIPWIRE tier2 ({'paper, no halt' if not cfg.get('live',False) else 'sudah halted'}): {' ; '.join(tw['reasons'])}")
        else:
            new_mult = tw['size_mult']
            if abs(new_mult-float(cfg.get('tripwire_size_mult',1.0)))>1e-6:
                set_config(tripwire_size_mult=new_mult)
                tag = "⚠️ TRIPWIRE tier1" if tw['tier']==1 else "✅ TRIPWIRE reset"
                ev.append(f"{tag}: {' ; '.join(tw['reasons']) or 'metrik pulih ke normal'} -> size x{new_mult}")
            if cfg.get('sleeves',{}).get('v20',True):
                # EKSEKUSI v20: rekonsiliasi ke posisi yg diinginkan (truth = posisi exchange)
                desired = sl['pos'] if sl['pos']!=0 else sl['pending']   # collapse pending -> entry same-run (fix timing)
                msg=sync_live("v20", desired, price)
                if msg: ev.append(msg)
    if ev: alert(ev)
    else:  print("  (tidak ada aksi bar ini)")
    st["last_open_time"]=last_ot; save_state(st); show_status(st)

def selftest():
    print("== SELFTEST v22 (v20-only): replay CSV ==")
    df=pd.read_csv(os.path.join(HERE,"btc_15m_full.csv"),parse_dates=['dt']); n=len(df)
    ctx=build_v20_context(df)
    sv=new_sleeve(); start=max(DEF['warmup'],DEF['ema_len']+2)
    for i in range(start,n):
        step_v20(sv,i,ctx)   # ai=None -> i absolut sepanjang CSV
    print(f"  v20 sleeve: ret {(sv['equity']-1)*100:+7.0f}%  trades {sv['ntr']}  WR {sv['nwin']/sv['ntr']*100:.1f}%   (target ~+3327/557/64.3)")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--once",action="store_true"); ap.add_argument("--status",action="store_true")
    ap.add_argument("--selftest",action="store_true"); ap.add_argument("--reset",action="store_true")
    ap.add_argument("--resume",action="store_true",help="clear circuit-breaker halt (live tetap OFF, nyalakan manual)")
    a=ap.parse_args()
    if a.reset: save_state(dict(v20=new_sleeve(),last_open_time=0)); print("state v22 direset.")
    elif a.resume:
        st=load_state(); st.setdefault('breaker',{})['halted']=False; st['breaker']['reason']=""
        st['v20']['loss_streak']=0; st['tripwire']={"tier":0,"reasons":[],"size_mult":1.0}
        save_state(st); set_config(halted=False, tripwire_size_mult=1.0)
        print("breaker+tripwire di-reset. LIVE tetap OFF — nyalakan manual via admin kalau yakin.")
    elif a.selftest: selftest()
    elif a.status: show_status()
    elif a.once:
        from bot_v20_funding import acquire_lock, release_lock
        lk=acquire_lock()
        if lk is None: print("⏭️ run lain masih jalan -> skip (cegah double-order)")
        else:
            try: do_once()
            finally: release_lock(lk)
    else: ap.print_help()
