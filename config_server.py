#!/usr/bin/env python3
"""BTC TERMINAL — PUBLIC market dashboard :8788. Multi-asset BTC/ETH/SOL. READ-ONLY (no keys, no trading).
Aman dishare/deploy publik. Kontrol trading privat ada di config_admin.py (localhost:8789)."""
import json, requests, urllib3, datetime, base64, os, subprocess, gzip, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, quote
urllib3.disable_warnings()
def _load_pass():   # S2: TANPA password hardcode di source (env TERMINAL_PASS > file .terminal_pass). None -> auth selalu tolak.
    p=os.environ.get("TERMINAL_PASS")
    if p: return p
    try:
        with open("/home/dnayaka/Documents/dynamic_rsi/btc-terminal/.terminal_pass") as f: return f.read().strip() or None
    except Exception: return None
AUTH_PASS=_load_pass()
# ===================== AUTH: shared user/session store (userdb.py) =====================
import time as _time   # dipakai rate-limit di bawah
from userdb import (load_users, add_user, del_user, set_expiry, is_expired, is_admin,
                    verify_user, list_users, make_session, session_user, del_session,
                    bootstrap_admin, SESS_TTL)
if bootstrap_admin("dnayaka", AUTH_PASS):   # admin pertama kalau users.json kosong (password = .terminal_pass)
    print("bootstrap admin: dnayaka / (password = .terminal_pass)")
# ---- anti-DDoS / brute-force: rate-limit per-IP (sliding window) + login throttle ----
_RL={}; _LF={}; _RLLK=threading.Lock()
def _rl_ok(ip, limit=140, window=10):   # max 140 req / 10s per IP -> else 429
    now=_time.time()
    with _RLLK:
        q=[t for t in _RL.get(ip,()) if t>now-window]
        if len(q)>=limit: _RL[ip]=q; return False
        q.append(now); _RL[ip]=q
        if len(_RL)>8000:
            for k in [k for k,v in _RL.items() if not v or v[-1]<now-window]: _RL.pop(k,None)
        return True
def _login_blocked(ip):   # max 8 gagal / 5mnt per IP
    now=_time.time()
    with _RLLK:
        q=[t for t in _LF.get(ip,()) if t>now-300]; _LF[ip]=q; return len(q)>=8
def _login_fail(ip):
    with _RLLK: _LF.setdefault(ip,[]).append(_time.time())
_JOBS={}; _JOBLK=threading.Lock()   # S4: single-flight subprocess (cegah spawn bertumpuk / korup file)
_FXLAST=[16000.0]   # H5: kurs USD/IDR terakhir-bagus (stale-on-error, jangan pin 16000 sejam)
STOCKS_DIR="/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks"
# ===== Trading journal (per-user notes + screenshot, privat) =====
import secrets as _secrets
_JHERE=os.path.dirname(os.path.abspath(__file__))
JOURNAL_F=os.path.join(_JHERE,"journal.json")
JIMG_DIR=os.path.join(_JHERE,"journal_imgs")
JCAP_ENTRIES=100; JCAP_IMG_BYTES=2*1024*1024
_JLK=threading.Lock()
def _jload():
    try:
        with open(JOURNAL_F) as f: return json.load(f)
    except Exception: return {}
def _jsave(d):
    tmp=JOURNAL_F+".tmp"
    fd=os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
    with os.fdopen(fd,"w") as f: json.dump(d,f)
    os.replace(tmp, JOURNAL_F)
def _detect_img(raw):
    """Sniff magic bytes -> ekstensi aman (JANGAN percaya nama-file/Content-Type dari client)."""
    if raw[:3]==b"\xff\xd8\xff": return "jpg"
    if raw[:8]==b"\x89PNG\r\n\x1a\n": return "png"
    if raw[:4]==b"RIFF" and raw[8:12]==b"WEBP": return "webp"
    return None
# ===== Price/RSI alerts (per-user, in-web only -- dicek client-side selama tab kebuka, TANPA WA/push) =====
ALERTS_F=os.path.join(_JHERE,"alerts.json")
ALERTS_CAP=30
_ALK=threading.Lock()
def _aload():
    try:
        with open(ALERTS_F) as f: return json.load(f)
    except Exception: return {}
def _asave(d):
    tmp=ALERTS_F+".tmp"
    fd=os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
    with os.fdopen(fd,"w") as f: json.dump(d,f)
    os.replace(tmp, ALERTS_F)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0'}); FAPI="https://fapi.binance.com"
import time as _time
_DFAIL=[0.0]; _DFAIL_LK=threading.Lock()   # ts terakhir direct gagal -> skip direct 5mnt
_STATSLAST={}   # stale-on-error /api/stats per-sym (fix: dulu upstream-fail -> cache nol 20dtk ke semua pengunjung)
# ===== concurrency hardening: thread-safe TTL cache + file/blob caches =====
_CACHE={}; _KEYLK={}; _CLK=threading.Lock()
_TFOK={"1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w"}   # whitelist tf (cegah unbounded cache key DoS)
_NEWSLAST={}; _NEWSLK=threading.Lock()   # last-good news per (sym,lang) -> stale-on-error
_LIQMAX={}; _LIQMAX_LK=threading.Lock()   # EMA-smoothed max per sym utk normalisasi /api/liqmap -- FIX brightness flicker
def _liqmax_smooth(sym, cur_max):
    """Normalisasi liqmap dulu pakai max() DARI BATCH SAAT ITU SAJA -> level harga sama bisa
    keliatan terang/gelap gonta-ganti antar-fetch cuma krn max-nya goyang, BUKAN krn datanya
    beneran berubah (bin borderline juga bisa nyebrang ambang 0.04 -> 'muncul-ngilang'). Fix:
    EMA-smooth max lintas-fetch (peredam noise 1-fetch, tetap ngikutin kalau rezim beneran geser)."""
    with _LIQMAX_LK:
        prev=_LIQMAX.get(sym, cur_max)
        smoothed=prev*0.7+cur_max*0.3
        _LIQMAX[sym]=smoothed
        return smoothed
_CALPATH="/home/dnayaka/Documents/dynamic_rsi/btc-terminal/cal_cache.json"   # ditulis cron cal_fetch.py; server CUMA baca (decouple dari traffic -> faireconomy ga ke-hammer)
def _cal_read():
    """(events_list, fetched_ts) dari cal_cache.json; ([],0) kalau belum ada."""
    try:
        with open(_CALPATH) as f: d=json.load(f)
        if isinstance(d,dict): return d.get("events",[]), d.get("fetched",0)
        return d, 0   # backward-compat (format lama = list polos)
    except Exception: return [], 0
def _cal_save(ev):
    try:
        import os as _os
        fd=_os.open(_CALPATH+".tmp", _os.O_CREAT|_os.O_WRONLY|_os.O_TRUNC, 0o644)
        with _os.fdopen(fd,"w") as f: json.dump({"events":ev,"fetched":int(_time.time())},f)
        _os.replace(_CALPATH+".tmp",_CALPATH)
    except Exception: pass
def _keylock(key):
    with _CLK:
        lk=_KEYLK.get(key)
        if lk is None: lk=threading.Lock(); _KEYLK[key]=lk
        return lk
def cache_get(key, ttl, producer):
    """Serve cached body for `key`; run producer() AT MOST once per ttl even under
    concurrent misses (per-key lock collapses the stampede). producer()->str/bytes."""
    now=_time.time()
    with _CLK:
        e=_CACHE.get(key)
        if e and e[0]>now: return e[1]
    with _keylock(key):                       # only ONE thread per key fetches upstream
        now=_time.time()
        with _CLK:
            e=_CACHE.get(key)
            if e and e[0]>now: return e[1]     # filled while we waited on the key lock
        val=producer()
        with _CLK: _CACHE[key]=(_time.time()+ttl, val)
        return val
_FC={}; _FLK=threading.Lock()
def file_get(fp, default="{}"):
    """File text cached by (mtime,size); re-read only when the file changes."""
    try: st=os.stat(fp); mt=(st.st_mtime, st.st_size)
    except OSError: return default
    with _FLK:
        e=_FC.get(fp)
        if e and e[0]==mt: return e[1]
    try:
        with open(fp) as f: d=f.read()
    except Exception: return default
    with _FLK: _FC[fp]=(mt, d)
    return d
_V20={"mt":0,"raw":b'{}',"gz":None}; _V20LK=threading.Lock()
_V20PATH="/home/dnayaka/Documents/dynamic_rsi/btc-terminal/btc_v20.json"
_MV20={"ETHUSDT":{"mt":0,"raw":b'{}',"gz":None},"SOLUSDT":{"mt":0,"raw":b'{}',"gz":None}}; _MV20LK=threading.Lock()
_MV20PATH={"ETHUSDT":"/home/dnayaka/Documents/dynamic_rsi/btc-terminal/eth_v20.json",
           "SOLUSDT":"/home/dnayaka/Documents/dynamic_rsi/btc-terminal/sol_v20.json"}
def multi_v20_blob(sym):
    """Sama pola v20_blob() tapi utk ETH/SOL (file terpisah, cache terpisah per-symbol)."""
    path=_MV20PATH.get(sym)
    if not path: return b'{}', None
    try: st=os.stat(path); mt=(st.st_mtime, st.st_size)
    except OSError: mt=None
    with _MV20LK:
        e=_MV20[sym]
        if e["gz"] is not None and e["mt"]==mt: return e["raw"], e["gz"]
        try:
            with open(path,"rb") as f: raw=f.read()
        except Exception: raw=b'{}'; mt=None
        gz=gzip.compress(raw,5)
        e["mt"]=mt; e["raw"]=raw; e["gz"]=gz
        return raw, gz
def v20_blob():
    """(raw_bytes, gzip_bytes) for btc_v20.json; re-read+re-gzip ONLY on mtime change.
    Lock held across rebuild = single-flight (no thundering 5MB read+gzip storm)."""
    try: st=os.stat(_V20PATH); mt=(st.st_mtime, st.st_size)
    except OSError: mt=None
    with _V20LK:
        if _V20["gz"] is not None and _V20["mt"]==mt: return _V20["raw"], _V20["gz"]
        try:
            with open(_V20PATH,"rb") as f: raw=f.read()
        except Exception: raw=b'{}'; mt=None
        gz=gzip.compress(raw,5)
        _V20["mt"]=mt; _V20["raw"]=raw; _V20["gz"]=gz
        return raw, gz
def _try(url, to):
    try:
        r=S.get(url, timeout=to, verify=False); j=r.json()
        return j if j not in (None,{},[]) else None
    except Exception: return None
def bget(path):
    """Binance fapi: direct (Proton ON, cepat) -> rantai 3 proxy publik (Proton OFF / 1 proxy lagi flap).
    Sticky: sekali direct gagal -> proxy-only 5mnt (no delay), retry direct tiap 5mnt.
    Fix 1-Jul: dulu cuma 1 proxy (cors.sh) -> LIQ/liqmap kadang hilang pas proxy itu flap sendirian.
    Return json/None."""
    D=FAPI+path
    with _DFAIL_LK: skip=_time.time()-_DFAIL[0] < 300
    if not skip:
        j=_try(D, 4)                                  # coba direct (timeout pendek)
        if j is not None: return j
        with _DFAIL_LK: _DFAIL[0]=_time.time()        # direct gagal -> tandai, pakai proxy 5mnt
    uq=quote(D, safe="")
    chain = ["https://proxy.cors.sh/"+D, "https://corsproxy.io/?url="+uq, "https://api.allorigins.win/raw?url="+uq]
    for i, url in enumerate(chain):                    # coba tiap proxy berurutan sampai ada yg jawab
        j=_try(url, 15 if i==0 else 12)
        if j is not None: return j
    return None
SYMS={"BTCUSDT","ETHUSDT","SOLUSDT"}; _G={"t":0,"d":{}}; NEWSTAG={"BTCUSDT":"bitcoin","ETHUSDT":"ethereum","SOLUSDT":"solana"}
def sym_of(p): s=parse_qs(p.query).get("sym",["BTCUSDT"])[0].upper(); return s if s in SYMS else "BTCUSDT"
import hashlib as _hl
_TRC={}; _TRC_LK=threading.Lock()   # cache terjemahan (key=md5(tl|text)) -> hemat call
def gtrans(text, tl="id"):
    """Terjemah teks via endpoint Google translate gtx (gratis, tanpa key). Cache. Gagal -> teks asli."""
    text=(text or "").strip()
    if not text: return text
    k=_hl.md5((tl+"|"+text).encode("utf-8")).hexdigest()
    v=_TRC.get(k)
    if v is not None: return v
    try:
        r=S.get("https://translate.googleapis.com/translate_a/single",
                params={"client":"gtx","sl":"auto","tl":tl,"dt":"t","q":text}, timeout=8, verify=False)
        j=r.json(); out="".join(seg[0] for seg in j[0] if seg and seg[0])
        if out:
            with _TRC_LK:
                if len(_TRC)>2000: _TRC.clear()
                _TRC[k]=out
            return out
    except Exception: pass
    return text

CSS=r"""
:root{--bg:#000000;--panel:#070707;--ink:#e8e2d0;--dim:#8a7f63;--faint:#3a3526;
--amber:#ff8c1a;--amber2:#ffb454;--glow:rgba(255,140,26,.45);--up:#27d07a;--down:#ff453a;--line:#1b1810;
--mono:'IBM Plex Mono',ui-monospace,monospace;--disp:'Bricolage Grotesque',sans-serif;}
*{margin:0;padding:0;box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{background:var(--bg);color:var(--ink);font-family:var(--mono);font-size:13px;line-height:1.35;overflow-x:hidden;letter-spacing:.01em}
.bg{position:fixed;inset:0;z-index:-3;background:radial-gradient(120% 70% at 50% -15%,rgba(255,140,26,.07),transparent 50%),radial-gradient(80% 60% at 90% 120%,rgba(39,208,122,.03),transparent 60%),var(--bg)}
.bg::before{content:"";position:absolute;inset:0;background-image:radial-gradient(rgba(255,140,26,.035) 1px,transparent 1px);background-size:34px 34px;-webkit-mask:radial-gradient(120% 80% at 50% 0%,#000,transparent 80%);mask:radial-gradient(120% 80% at 50% 0%,#000,transparent 80%)}
.scan{position:fixed;inset:0;z-index:-2;pointer-events:none;background:repeating-linear-gradient(0deg,transparent 0 2px,rgba(0,0,0,.22) 2px 3.5px);opacity:.4;mix-blend-mode:multiply}
.grain{position:fixed;inset:0;z-index:99;pointer-events:none;opacity:.035;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
.vig{position:fixed;inset:0;z-index:-1;pointer-events:none;box-shadow:inset 0 0 200px 30px rgba(0,0,0,.8)}
.boot{position:fixed;left:0;right:0;top:0;height:2px;background:linear-gradient(90deg,transparent,var(--amber),transparent);z-index:200;animation:boot 1s ease-out forwards}
@keyframes boot{0%{top:0;opacity:1}100%{top:100%;opacity:0}}
.wrap{max-width:1200px;margin:0 auto;padding:0 clamp(14px,3vw,28px) 50px}
.label{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim)}
.up{color:var(--up)}.down{color:var(--down)}.amber{color:var(--amber)}
.fnbar{display:flex;gap:0;border-bottom:1px solid var(--line);font-size:10px;letter-spacing:.12em;color:var(--dim);overflow-x:auto}
.fnbar span{padding:5px 12px;border-right:1px solid var(--line);white-space:nowrap;text-transform:uppercase}
.fnbar span b{color:var(--amber);font-weight:600}
.hdr{display:flex;justify-content:space-between;align-items:center;padding:13px 0;border-bottom:1px solid var(--line);position:sticky;top:0;background:rgba(0,0,0,.88);backdrop-filter:blur(6px);z-index:50}
.brand{font-family:var(--disp);font-weight:700;font-size:15px;letter-spacing:-.01em;display:flex;align-items:center;gap:8px;color:var(--ink)}
.brand .bt{color:var(--amber);font-size:18px;text-shadow:0 0 12px var(--glow)}
.brand .cur{display:inline-block;width:8px;height:15px;background:var(--amber);margin-left:2px;animation:blink 1.1s step-end infinite;box-shadow:0 0 9px var(--glow)}
@keyframes blink{50%{opacity:0}}
.hdr .r{display:flex;align-items:center;gap:12px;font-size:10.5px;color:var(--dim)}
.tag{padding:3px 9px;border:1px solid var(--line);border-radius:2px;letter-spacing:.14em;font-size:10px;color:var(--amber)}
.symbar{display:flex;align-items:center;gap:10px;margin:18px 0 0;flex-wrap:wrap}
.symseg{display:flex;border:1px solid var(--line);border-radius:5px;overflow:hidden}
.symseg button{background:transparent;color:var(--dim);border:0;border-right:1px solid var(--line);padding:9px 20px;font-family:var(--disp);font-weight:600;font-size:15px;cursor:pointer;transition:.2s}
.symseg button:last-child{border-right:0}.symseg button:hover{color:var(--ink);background:rgba(255,140,26,.06)}
.symseg button.act{color:#160c00;background:var(--amber)}
/* hero — more breathing room for the ticker */
.hero{padding:30px 0 26px}
.bigprice{font-family:var(--mono);font-weight:600;font-size:clamp(46px,11vw,104px);line-height:1;letter-spacing:-.03em;margin:0 0 12px;font-variant-numeric:tabular-nums;color:var(--ink);text-shadow:0 0 44px rgba(255,140,26,.14);white-space:nowrap}
.bigprice.flash{animation:flash .5s}@keyframes flash{0%{color:var(--amber2);text-shadow:0 0 54px var(--glow)}100%{}}
.pxsub{font-size:14px;color:var(--dim)}.pxsub b{font-weight:600;font-variant-numeric:tabular-nums}
.gauges{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:9px;margin-top:24px}
.gauge{background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:12px 14px;position:relative;overflow:hidden}
.gauge::after{content:"";position:absolute;left:0;top:0;width:2px;height:100%;background:var(--amber);opacity:.7}
.gauge .g-l{font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.gauge .g-v{font-family:var(--mono);font-weight:600;font-size:20px;margin-top:5px;font-variant-numeric:tabular-nums}
.fngbar{height:3px;border-radius:2px;background:var(--faint);margin-top:8px;overflow:hidden}
.fngbar i{display:block;height:100%;background:linear-gradient(90deg,var(--down),var(--amber),var(--up));width:0;transition:width 1s}
.grid{display:grid;grid-template-columns:1fr;gap:10px;margin-top:10px}
@media(min-width:880px){.grid{grid-template-columns:1.6fr 1fr}.span2{grid-column:1/3}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px;position:relative}
.panel-h{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px}
.panel-h .t{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--amber);display:flex;align-items:center;gap:7px}
.panel-h .t .sq{width:5px;height:5px;background:var(--amber);box-shadow:0 0 7px var(--glow)}
.aibias{font-size:9px;letter-spacing:.12em;text-transform:uppercase;padding:3px 8px;border:1px solid var(--line);border-radius:3px;color:var(--dim)}
.aibias.bullish{color:var(--up);border-color:rgba(39,208,122,.4)}.aibias.bearish{color:var(--down);border-color:rgba(255,69,58,.4)}.aibias.netral{color:var(--amber);border-color:rgba(255,140,26,.35)}
.aibody .cm{font-size:13px;line-height:1.6;color:var(--ink)}.aibody ul{margin:10px 0 0;padding-left:16px}.aibody li{font-size:12px;color:var(--dim);line-height:1.7}
.aibody .off{font-size:12px;color:var(--dim)}.aibody .stamp{font-size:10px;color:var(--dim);margin-top:9px;letter-spacing:.08em}
.ctrls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.seg{display:flex;gap:3px}
.seg button{background:transparent;color:var(--dim);border:1px solid var(--line);padding:4px 10px;border-radius:3px;font-family:var(--mono);font-size:10.5px;cursor:pointer;transition:.2s;letter-spacing:.05em}
.seg button:hover{color:var(--ink);border-color:var(--faint)}.seg button.act{color:var(--amber);border-color:var(--amber);background:rgba(255,140,26,.08)}
#chart{height:340px;border-radius:4px;overflow:hidden}
#rsi{height:100px;border-radius:4px;overflow:hidden;margin-top:3px;border-top:1px solid var(--line)}
.rsi-l{font-size:9px;letter-spacing:.14em;color:var(--dim);margin:5px 0 -2px;text-transform:uppercase}
.liqbar{height:28px;border-radius:4px;overflow:hidden;display:flex;margin:4px 0 12px;border:1px solid var(--line);position:relative}
.liqbar::after{content:'';position:absolute;left:50%;top:0;bottom:0;width:2px;background:rgba(255,255,255,.4);transform:translateX(-1px);pointer-events:none}
.liqbar .b{background:linear-gradient(90deg,rgba(39,208,122,.12),rgba(39,208,122,.4));display:flex;align-items:center;padding:0 9px;font-size:10.5px;color:var(--up);font-weight:600;transition:flex .8s}
.liqbar .a{background:linear-gradient(90deg,rgba(255,69,58,.4),rgba(255,69,58,.12));display:flex;align-items:center;justify-content:flex-end;padding:0 9px;font-size:10.5px;color:var(--down);font-weight:600;transition:flex .8s}
.liqrow{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid var(--line);font-size:12.5px}
.liqrow:last-child{border-bottom:0}.liqrow .k{color:var(--dim);font-size:10px;letter-spacing:.1em;text-transform:uppercase;flex-shrink:0}.liqrow .v{font-weight:600;font-variant-numeric:tabular-nums;flex:1;min-width:0;text-align:right}
.wall{display:flex;justify-content:space-between;font-size:11.5px;color:var(--dim);padding:5px 0}.wall b{color:var(--ink)}
.statg{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.statg .s{background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:11px 12px}
.statg .s .k{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
.statg .s .v{font-size:17px;font-weight:600;margin-top:4px;font-variant-numeric:tabular-nums}
.wire a{display:grid;grid-template-columns:auto 1fr;gap:11px;padding:10px 0;border-bottom:1px solid var(--line);color:var(--ink);text-decoration:none;font-size:13px;line-height:1.4;transition:.2s}
.wire a:hover{color:var(--amber2);padding-left:5px}.wire a:last-child{border-bottom:0}
.wire a .ago{font-size:9.5px;color:var(--amber);letter-spacing:.1em;padding-top:2px;min-width:32px}.wire a .src{font-size:9.5px;color:var(--dim)}
/* news panel (cohesive Bloomberg) */
.newssum{margin-bottom:12px}.newssum:empty{display:none;margin:0}
.nsumwrap{padding-bottom:11px;border-bottom:1px solid var(--line)}
.nsum-h{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--amber);margin-bottom:8px}
.nsum-list{margin:0;padding-left:16px}.nsum-list li{font-size:12px;color:var(--dim);line-height:1.7}
.nrow{display:grid;grid-template-columns:auto 1fr auto;gap:11px;padding:10px 0;border-bottom:1px solid var(--line);color:var(--ink);cursor:pointer;font-size:13px;line-height:1.4;transition:.2s}
.nrow:hover{color:var(--amber2);padding-left:5px}.nrow.open{color:var(--amber);border-bottom:0}
.nrow .ago{font-size:9.5px;color:var(--amber);letter-spacing:.1em;padding-top:2px;min-width:32px;white-space:nowrap}
.nrow .ttl{align-self:center}.nrow .src{display:block;font-size:9.5px;color:var(--dim);margin-top:3px}
.nrow .nchev{align-self:center;font-size:9px;color:var(--dim);transition:transform .2s,color .2s}
.nrow:hover .nchev{color:var(--amber2)}.nrow.open .nchev{transform:rotate(180deg);color:var(--amber)}
.ndet{display:none;padding:0 0 12px 43px;border-bottom:1px solid var(--line)}.ndet.open{display:block}
.ndet .nsum{font-size:12px;line-height:1.6;color:var(--ink);margin-bottom:9px}.ndet .noff{font-size:12px;line-height:1.6;color:var(--dim);margin-bottom:9px}
.nvisit{display:inline-block;color:var(--amber);text-decoration:none;font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;border:1px solid var(--line);padding:5px 11px;border-radius:3px;transition:.2s}
.nvisit:hover{border-color:var(--amber);background:rgba(255,140,26,.08);color:var(--amber2)}
.nitem:last-child .nrow,.nitem:last-child .ndet{border-bottom:0}.nempty{color:var(--dim);font-size:12px;padding:9px 0}
.trbtn{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;padding:4px 9px;border:1px solid var(--line);border-radius:3px;color:var(--dim);background:transparent;cursor:pointer;transition:.2s}
.trbtn:hover{color:var(--amber2);border-color:var(--amber)}.trbtn.act{color:#160c00;background:var(--amber);border-color:var(--amber)}
/* liq legend (collapsible, mobile-friendly) */
#liqLegend{display:none;position:absolute;top:8px;left:8px;z-index:5;background:rgba(12,10,6,.9);border:1px solid var(--line);border-radius:6px;color:#cbb98e;font-size:10.5px;line-height:1.5;max-width:215px;overflow:hidden}
#liqHdr{padding:6px 9px;cursor:pointer;display:flex;align-items:center;gap:7px;white-space:nowrap;user-select:none}
#liqHdr .lt{color:var(--amber2);letter-spacing:.1em}
#liqChev{margin-left:auto;color:var(--dim);transition:transform .2s}
#liqLegend.open #liqChev{transform:rotate(180deg)}
#liqDet{display:none;padding:0 9px 8px;border-top:1px solid var(--line);font-size:10px}
#liqLegend.open #liqDet{display:block;padding-top:7px}
@media(max-width:640px){#liqLegend{font-size:9.5px;max-width:64vw;top:6px;left:6px}#liqHdr{padding:5px 7px;gap:5px}}
#rpBar{display:none;position:absolute;bottom:12px;left:50%;transform:translateX(-50%);z-index:6;background:rgba(12,10,6,.94);border:1px solid var(--line);border-radius:9px;padding:7px 11px;align-items:center;gap:9px;font-size:11px;color:var(--ink);box-shadow:0 8px 26px rgba(0,0,0,.6)}
.rpb{background:transparent;border:1px solid var(--line);border-radius:5px;color:var(--ink);cursor:pointer;padding:4px 9px;font-size:13px;line-height:1;transition:.15s}.rpb:hover{border-color:var(--amber);color:var(--amber2)}
.mini{margin-left:auto;cursor:pointer;color:var(--dim);font-size:15px;line-height:1;padding:2px 7px;border:1px solid var(--line);border-radius:4px;user-select:none;transition:.15s;flex:none}
.mini:hover{color:var(--amber);border-color:var(--amber)}
.panel.collapsed>:not(.panel-h){display:none!important}.panel.collapsed{padding-bottom:13px}.panel.collapsed .panel-h{margin-bottom:0}
.ctgl{background:transparent;border:1px solid var(--line);border-radius:5px;color:var(--dim);cursor:pointer;padding:3px 9px;font-size:13px;line-height:1;transition:.15s}.ctgl:hover{color:var(--amber);border-color:var(--amber)}
.ctrls.min .seg{display:none}.ctrls.min #ctrlsTgl{color:var(--amber);border-color:var(--amber)}
.panel.maxi{position:fixed;inset:0;z-index:200;max-width:none;margin:0;border-radius:0;overflow:hidden;display:flex;flex-direction:column;background:var(--bg)}
.panel.maxi .panel-h{flex:none}.panel.maxi #chart{flex:1;height:auto!important;min-height:0}.panel.maxi #rsi{height:130px!important}
#maxBtn.act{color:var(--amber);border-color:var(--amber)}
/* oscillator panes (MACD/Stoch) — mirror #rsi */
#macd,#stoch{height:96px;border-radius:4px;overflow:hidden;margin-top:3px;border-top:1px solid var(--line);display:none}
/* indikator menu (TradingView-style fx) */
#indWrap{position:relative}
#indMenu{display:none;position:absolute;top:32px;left:0;z-index:60;background:rgba(10,9,6,.98);border:1px solid var(--line);border-radius:8px;padding:9px 12px;min-width:236px;box-shadow:0 16px 44px rgba(0,0,0,.75)}
#indMenu.open{display:block}
#indMenu .imh{font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--amber);margin:9px 0 4px}#indMenu .imh:first-child{margin-top:0}
#indMenu .irow{display:flex;align-items:center;gap:7px;padding:4px 0;font-size:11.5px;color:var(--ink);cursor:pointer;white-space:nowrap}
#indMenu .irow input[type=checkbox]{accent-color:var(--amber);cursor:pointer;width:13px;height:13px}
#indMenu .inp-n{width:36px;background:var(--bg);border:1px solid var(--line);border-radius:3px;color:var(--ink);font-family:var(--mono);font-size:10.5px;padding:2px 4px;text-align:center}
#indMenu .irow .inp-n:first-of-type{margin-left:auto}#indMenu .inp-n+.inp-n{margin-left:4px}
#indBtn{font-style:italic;font-weight:600}
/* HP: maximize chart = perbesar INLINE (bukan fullscreen yg ngejebak) */
@media(max-width:640px){
 .panel.maxi{position:static;inset:auto;z-index:auto;height:auto;border-radius:8px;display:block;overflow:visible}
 .panel.maxi #chart{flex:none;height:64vh!important}
 .panel.maxi #rsi{height:92px!important}.panel.maxi #macd,.panel.maxi #stoch{height:82px!important}
 #indMenu{min-width:208px}
 /* nav -> hamburger dropdown di HP (matikan deret link yg scroll ke kanan) */
 .hdr .r{position:relative}
 .hdr .navtog{display:block}
 .hdr .navwrap{display:none;position:absolute;top:calc(100% + 9px);right:0;flex-direction:column;align-items:stretch;gap:8px;background:rgba(10,9,6,.98);border:1px solid var(--line);border-radius:8px;padding:11px;min-width:168px;box-shadow:0 16px 44px rgba(0,0,0,.75);z-index:60}
 .hdr .navwrap.open{display:flex}
 .navwrap .navlink{text-align:center;padding:8px 11px}
 .navwrap .tag{text-align:center}
}
.foot{margin-top:26px;padding-top:16px;border-top:1px solid var(--line);display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px}
.foot span{font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint)}
.rv{opacity:0;transform:translateY(14px);animation:rv .7s cubic-bezier(.2,.8,.2,1) forwards}@keyframes rv{to{opacity:1;transform:none}}
.d1{animation-delay:.1s}.d2{animation-delay:.2s}.d3{animation-delay:.3s}.d4{animation-delay:.4s}.d5{animation-delay:.5s}
::selection{background:var(--amber);color:#0a0700}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:var(--line);border-radius:4px}
@media(max-width:620px){.gauges{grid-template-columns:1fr 1fr}.bigprice{white-space:normal}.liqrow{font-size:11.5px}.liqrow .v{font-size:11px;line-height:1.4}}
.idx-strip{display:flex;flex-wrap:wrap;gap:7px 18px;font-size:12px;padding:4px 0 11px;border-bottom:1px solid var(--line);margin-bottom:11px;font-variant-numeric:tabular-nums}
.idx-strip .k{color:var(--dim);font-size:9px;letter-spacing:.1em;text-transform:uppercase}
.idx-strip b{color:var(--ink);font-weight:600}
.sigwarn{background:rgba(255,69,58,.1);border:1px solid rgba(255,69,58,.45);color:var(--down);border-radius:5px;padding:10px 13px;font-size:12px;margin-bottom:11px;font-weight:600;line-height:1.5}
.sigwarn b{color:#ff8f86}
.sigok{background:rgba(39,208,122,.09);border:1px solid rgba(39,208,122,.4);color:var(--up);border-radius:5px;padding:10px 13px;font-size:12px;margin-bottom:11px;line-height:1.5}
.sigrow{display:flex;gap:11px;align-items:baseline;flex-wrap:wrap;padding:9px 11px;border-radius:4px;font-size:12.5px;margin-bottom:5px;border:1px solid var(--line);border-left-width:3px}
.sigrow.warn{border-left-color:var(--down)}.sigrow.ok{border-left-color:var(--up)}
.sigrow .sym{font-family:var(--disp);font-weight:700;font-size:14px;color:var(--amber);min-width:60px}
.nosig{font-size:12px;color:var(--dim);padding:9px 0;line-height:1.5}
.watch-h{font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--dim);margin:14px 0 9px;border-top:1px solid var(--line);padding-top:11px}
.watchgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(225px,1fr));gap:7px}
.wrow .wb{color:var(--dim);font-size:10px;line-height:1.45;margin-top:3px;border-top:1px solid var(--line);padding-top:4px}
.wrow .wb b{color:var(--amber2);font-weight:600}
.wrow{display:flex;flex-direction:column;gap:2px;font-size:11px;padding:7px 9px;background:var(--bg);border:1px solid var(--line);border-radius:4px;border-left:2px solid var(--faint)}
.wrow.ready{border-left-color:var(--amber)}
.wrow .ws{font-family:var(--disp);font-weight:600;font-size:13px;color:var(--ink)}
.wrow .wm{color:var(--dim);font-size:10px;line-height:1.35}
.wrow{cursor:pointer;transition:.15s}.wrow:hover{border-color:var(--amber);background:rgba(255,140,26,.05)}
.navlink{color:var(--amber);text-decoration:none;font-size:10.5px;letter-spacing:.12em;border:1px solid var(--line);padding:5px 11px;border-radius:3px;transition:.2s}
.navlink:hover{border-color:var(--amber);background:rgba(255,140,26,.08)}
.navtog{display:none;background:transparent;border:1px solid var(--line);color:var(--amber);border-radius:3px;padding:3px 9px;font-size:15px;line-height:1.1;cursor:pointer;transition:.2s}
.navtog:hover{border-color:var(--amber);background:rgba(255,140,26,.08)}
.navwrap{display:flex;align-items:center;gap:12px}
.mfbox{display:flex;gap:12px;font-size:11px;flex-wrap:wrap;align-items:center}
.mfbox .mfi{padding:2px 8px;border:1px solid var(--line);border-radius:10px;font-size:10px}
.mfbox .acc{color:var(--up);border-color:rgba(39,208,122,.4)}.mfbox .dis{color:var(--down);border-color:rgba(255,69,58,.4)}.mfbox .neu{color:var(--amber)}
.bsbar{height:6px;border-radius:3px;display:flex;overflow:hidden;width:120px;border:1px solid var(--line)}
.bsbar .bb{background:rgba(39,208,122,.5)}.bsbar .ss{background:rgba(255,69,58,.45)}
.aibandar1{font-size:12px;color:var(--ink);line-height:1.5;margin-top:10px;padding-top:9px;border-top:1px solid var(--line)}
.sigrow.sel,.wrow.sel{border-color:var(--amber);box-shadow:0 0 0 1px var(--amber) inset}
.ffgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.ff-h{font-size:10px;letter-spacing:.14em;text-transform:uppercase;margin-bottom:8px;font-weight:600}
.ffcol .fr{display:flex;justify-content:space-between;padding:6px 9px;border:1px solid var(--line);border-radius:4px;margin-bottom:4px;font-size:12.5px}
.ffcol .fr b{font-variant-numeric:tabular-nums}.ffcol .fr .s{font-family:var(--disp);font-weight:600}
.calrow{padding:8px 0;border-bottom:1px solid var(--line)}.calrow:last-child{border-bottom:0}
.calhd{display:flex;justify-content:space-between;gap:10px;font-size:12.5px;font-weight:600;align-items:baseline}
.calt{color:var(--amber2);font-size:10.5px;white-space:nowrap;font-variant-numeric:tabular-nums}
.calmeta{font-size:11px;color:var(--dim);margin-top:2px}.calmeta b{color:var(--ink)}
.calnote{font-size:11.5px;color:var(--dim);margin-top:4px;line-height:1.5}
.caldet{display:none}.caldet.open{display:block}
"""
FAVICON_SVG=("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
 "<rect width='64' height='64' rx='14' fill='#0a0700'/>"
 "<rect x='2' y='2' width='60' height='60' rx='12' fill='none' stroke='#ff8c1a' stroke-width='3'/>"
 "<text x='32' y='46' font-family='Arial,Helvetica,sans-serif' font-size='36' font-weight='700' fill='#ff8c1a' text-anchor='middle'>₿</text>"
 "</svg>")
import urllib.parse as _fuq
FAVICON_DATAURI="data:image/svg+xml,"+_fuq.quote(FAVICON_SVG)

# ===== PWA (installable "Add to Home Screen") =====
_ICON_DIR=os.path.join(_JHERE,"icons")
def _read_icon(name):
    try:
        with open(os.path.join(_ICON_DIR,name),"rb") as f: return f.read()
    except Exception: return b""
ICON_192=_read_icon("icon-192.png"); ICON_512=_read_icon("icon-512.png")
PWA_MANIFEST=json.dumps({
    "name":"DNAYAKA Crypto Terminal","short_name":"BTC Terminal",
    "start_url":"/","display":"standalone","background_color":"#0a0700","theme_color":"#0a0700",
    "description":"Bloomberg-style BTC/ETH/SOL trading terminal — live chart, journal, alerts",
    "icons":[{"src":"/icons/icon-192.png","sizes":"192x192","type":"image/png","purpose":"any maskable"},
             {"src":"/icons/icon-512.png","sizes":"512x512","type":"image/png","purpose":"any maskable"}]
})
SW_JS=("const CACHE='dnayaka-terminal-v1';"
"self.addEventListener('install',e=>self.skipWaiting());"
"self.addEventListener('activate',e=>self.clients.claim());"
"self.addEventListener('fetch',e=>{});")   # no offline caching (data harus selalu live) -- SW cuma buat installability
HEAD=("<!doctype html><html lang=en><head><meta charset=utf-8>"
"<meta name=viewport content='width=device-width,initial-scale=1'>"
f"<link rel=icon type=image/svg+xml href=\"{FAVICON_DATAURI}\">"
"<link rel=manifest href=/manifest.json>"
"<link rel=apple-touch-icon href=/icons/icon-192.png>"
"<meta name=theme-color content=#0a0700><meta name=apple-mobile-web-app-capable content=yes>"
"<meta name=apple-mobile-web-app-status-bar-style content=black-translucent>"
"<script>if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});</script>"
"<script src='https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js'></script>"
"<link rel=preconnect href=https://fonts.googleapis.com><link rel=preconnect href=https://fonts.gstatic.com crossorigin>"
"<link href='https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,300..800&family=IBM+Plex+Mono:wght@300;400;500;600;700&display=swap' rel=stylesheet>"
"<style>"+CSS+"</style>")
ATMOS="<div class=bg></div><div class=scan></div><div class=vig></div><div class=grain></div><div class=boot></div>"
MAIN=HEAD+"<title>DNAYAKA · Crypto Terminal</title></head><body>"+ATMOS+r"""
<div class=fnbar><span><b>F1</b> MARKETS</span><span><b>F2</b> CHART</span><span><b>F3</b> LIQUIDITY</span><span><b>F4</b> STATS</span><span><b>F5</b> NEWS</span><span id=fnclock style="margin-left:auto;color:var(--amber)"></span></div>
<div class=wrap>
 <header class=hdr><div class=brand><span class=bt>₿</span> DNAYAKA<span style="color:var(--dim);font-weight:400;font-size:11px;letter-spacing:.18em;text-transform:uppercase;margin-left:9px">Crypto Terminal</span><span class=cur></span></div>
  <div class=r><button class=navtog aria-label=Menu onclick="this.nextElementSibling.classList.toggle('open')">☰</button><div class=navwrap><a class=navlink href="/journal">JOURNAL</a><a class=navlink href="/logout">LOGOUT</a><span class=tag>PUBLIC · LIVE</span></div></div></header>
 <div class=symbar>
   <div class=symseg id=symSeg><button data-s=BTCUSDT class=act>BTC</button><button data-s=ETHUSDT>ETH</button><button data-s=SOLUSDT>SOL</button></div>
   <span class=label id=symlbl>perpetual · binance futures</span>
 </div>
 <section class=hero>
  <div class=bigprice id=px>------</div>
  <div class="pxsub rv d1"><b id=chg>—</b> 24H &nbsp;·&nbsp; MARK <b id=mark>—</b></div>
  <div class=gauges>
   <div class="gauge rv d2"><div class=g-l>Funding 8h</div><div class=g-v id=funding>—</div></div>
   <div class="gauge rv d3"><div class=g-l>Fear &amp; Greed</div><div class=g-v id=fng>—</div><div class=fngbar><i id=fngbar></i></div></div>
   <div class="gauge rv d4"><div class=g-l>Open Interest</div><div class=g-v id=oi style="font-size:16px">—</div></div>
   <div class="gauge rv d5"><div class=g-l>Long / Short</div><div class=g-v id=ls style="font-size:16px">—</div></div>
   <div class="gauge rv d5"><div class=g-l>BTC Dominance</div><div class=g-v id=dom style="font-size:18px">—</div><div class=fngbar><i id=dombar></i></div></div>
  </div>
 </section>
 <section class="panel rv d2" style="margin-top:16px">
  <div class=panel-h><span class=t><span class=sq></span>Alert · Price/RSI (web — selama tab kebuka)</span></div>
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px">
   <select id=alSym style="background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:9px"><option value=BTCUSDT>BTC</option><option value=ETHUSDT>ETH</option><option value=SOLUSDT>SOL</option></select>
   <select id=alType style="background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:9px"><option value=price>Harga</option><option value=rsi>RSI (15m)</option></select>
   <select id=alOp style="background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:9px"><option value=">=">≥</option><option value="<=">≤</option></select>
   <input id=alVal type=number step=any placeholder="nilai" style="flex:1;min-width:100px;background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:9px">
   <button onclick=addAlert() style="padding:9px 16px;font-family:var(--mono);font-weight:600;letter-spacing:.06em;text-transform:uppercase;background:transparent;color:var(--amber);border:1px solid var(--amber);border-radius:6px;cursor:pointer;font-size:11px">+ Tambah</button>
  </div>
  <div id=alMsg style="font-size:10.5px;color:var(--dim);margin-bottom:6px"></div>
  <div id=alList style="display:flex;flex-direction:column;gap:6px">memuat…</div>
  <p style="font-size:10.5px;color:var(--dim);margin-top:8px;line-height:1.5">⚠️ Alert ini dicek di browser (bukan WhatsApp/push) — cuma jalan selama tab situs ini terbuka. Sekali kena, otomatis nonaktif (nggak spam berulang).</p>
 </section>
 <section class="panel rv d2" style="margin-top:16px">
  <div class=panel-h><span class=t><span class=sq></span>Perbandingan BTC / ETH / SOL</span></div>
  <div id=cmpGrid style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:12px;min-width:480px">
   <thead><tr style="border-bottom:1px solid var(--line);text-align:left;color:var(--dim);font-size:10.5px;text-transform:uppercase;letter-spacing:.06em">
    <th style="padding:6px 8px 8px 0">Metrik</th><th style="padding:6px 8px">₿ BTC</th><th style="padding:6px 8px">Ξ ETH</th><th style="padding:6px 8px">◎ SOL</th></tr></thead>
   <tbody id=cmpBody><tr><td colspan=4 style="padding:12px 0;color:var(--dim)">memuat…</td></tr></tbody>
  </table></div>
 </section>
 <div class=grid>
  <section class="panel span2 rv d2">
   <div class=panel-h><span class=t><span class=sq></span><span id=chtitle>BTC · Price Action</span></span>
    <div class=ctrls><button id=ctrlsTgl class=ctgl title="minimize / maximize toolbar">≡</button><div class=seg id=typeSeg><button data-ty=candle class=act>Candles</button><button data-ty=line>Line</button></div>
     <div class=seg id=tfSeg><button data-tf=1m>1m</button><button data-tf=3m>3m</button><button data-tf=5m>5m</button><button data-tf=15m class=act>15m</button><button data-tf=1h>1h</button><button data-tf=4h>4h</button><button data-tf=1d>1d</button></div>
     <div class="seg" id=indWrap><button id=indBtn title="Indikator (EMA/MA/Bollinger/Ichimoku/RSI/Volume/MACD/Stoch)">&fnof;x</button>
      <div id=indMenu>
       <div class=imh>Overlay</div>
       <label class=irow><input type=checkbox data-ind=ema> EMA<input class=inp-n type=number data-p="ema.p" min=1 value=20></label>
       <label class=irow><input type=checkbox data-ind=sma> MA (SMA)<input class=inp-n type=number data-p="sma.p" min=1 value=50></label>
       <label class=irow><input type=checkbox data-ind=bb> Bollinger<input class=inp-n type=number data-p="bb.p" min=1 value=20><input class=inp-n type=number data-p="bb.k" min=1 step=0.1 value=2></label>
       <label class=irow><input type=checkbox data-ind=ichi> Ichimoku</label>
       <div class=imh>Oscillator (pane)</div>
       <label class=irow><input type=checkbox data-ind=rsi> RSI<input class=inp-n type=number data-p="rsi.p" min=2 value=14></label>
       <label class=irow><input type=checkbox data-ind=vol> Volume</label>
       <label class=irow><input type=checkbox data-ind=macd> MACD<input class=inp-n type=number data-p="macd.f" min=1 value=12><input class=inp-n type=number data-p="macd.s" min=1 value=26><input class=inp-n type=number data-p="macd.sig" min=1 value=9></label>
       <label class=irow><input type=checkbox data-ind=stoch> Stoch<input class=inp-n type=number data-p="stoch.k" min=1 value=14><input class=inp-n type=number data-p="stoch.d" min=1 value=3></label>
      </div></div>
     <div class=seg id=sigSeg><button id=sigBtn title="Visual buy/sell strategi v20 (BTC)">BUY/SELL</button></div>
     <div class=seg id=liqSeg><button id=liqBtn title="Liquidation heatmap STANDAR (estimasi proyeksi leverage) — magnet harga">LIQ</button></div>
     <div class=seg id=liqRealSeg><button id=liqRealBtn title="EXPERIMENTAL — likuidasi NYATA (Coinalyze, 30hr): di mana likuidasi BENERAN terjadi per harga. Beda dari LIQ yg cuma proyeksi/estimasi.">LIQ*</button></div>
     <div class=seg id=wallSeg><button id=wallBtn title="Tembok order book ASLI (live, limit gede) = S/R. ijo=bid/support, merah=ask/resist">WALL</button></div>
     <div class=seg id=bookSeg><button id=bookBtn title="EXPERIMENTAL — order book RECORDER: rekam resting liquidity dari waktu→waktu (melebar pelan, bisa di-spoof, butuh cron jalan). Profil sisi kanan: hijau=bid/beli, merah=ask/jual.">BOOK*</button></div>
     <div class=seg id=snrSeg><button id=snrBtn title="Support/Resistance auto (pivot price-action, N× = jumlah touch)">SNR</button></div>
     <div class=seg id=rpSeg><button id=rpBtn title="Replay bar-per-bar (ala TradingView)">REPLAY</button></div>
     <div class=seg id=curSeg><button id=curBtn title="Konversi harga USD / IDR">USD</button></div></div><button id=maxBtn class=ctgl title="maximize / restore chart" style="margin-left:6px">⤢</button></div>
   <div id=chart style=position:relative><div id=liqLegend><div id=liqHdr onclick="$('liqLegend').classList.toggle('open')"><b class=lt id=liqTitle>LIQ</b><span>L <b id=liqTopL style="color:var(--up)">—</b> · S <b id=liqTopS style="color:var(--down)">—</b></span><span id=liqChev>▾</span></div><div id=liqDet><span style="color:var(--up)">▬</span> bawah = <b>long ke-liq</b> (harga turun→likuidasi)<br><span style="color:var(--down)">▬</span> atas = <b>short ke-liq</b> (harga naik→likuidasi)<br>makin <b>terang</b> = klaster gede → <b>magnet harga</b><br><span style="color:var(--dim)" id=liqMode>*estimasi proyeksi leverage 10–100x, bukan data exchange</span></div></div><div id=liqTip style="display:none;position:absolute;z-index:9;background:rgba(10,9,6,.96);border:1px solid var(--line);border-radius:6px;padding:8px 11px;font-size:11px;line-height:1.6;color:var(--ink);pointer-events:none;box-shadow:0 8px 24px rgba(0,0,0,.5);white-space:nowrap"></div><div id=rpBar><button id=rpBack class=rpb title="mundur 1 bar">⏮</button><button id=rpPlay class=rpb style="color:var(--amber);font-size:15px">▶</button><button id=rpFwd class=rpb title="maju 1 bar">⏭</button><span id=rpSpd class=rpb title="ganti kecepatan" style="color:var(--amber);min-width:34px;text-align:center">2×</span><span id=rpInfo style="color:var(--dim);min-width:140px;text-align:center">klik chart → titik mulai</span><button id=rpExit class=rpb title="keluar" style="color:var(--down)">✕</button></div></div><div class=rsi-l id=rsiLbl>RSI · 14</div><div id=rsi></div><div class=rsi-l id=macdLbl style=display:none>MACD · 12 26 9</div><div id=macd></div><div class=rsi-l id=stochLbl style=display:none>STOCH · 14 3</div><div id=stoch></div>
  </section>
  <section class="panel rv d3">
   <div class=panel-h><span class=t><span class=sq></span>Liquidity · Order Book</span></div>
   <div class=label>Bid vs Ask depth (±2%)</div>
   <div class=liqbar><div class=b id=lqb style="flex:1"></div><div class=a id=lqa style="flex:1"></div></div>
   <div class=wall><span>BID WALL</span><span><b id=bidwall>—</b></span></div>
   <div class=wall><span>ASK WALL</span><span><b id=askwall>—</b></span></div>
   <div class=liqrow><span class=k>Open Interest</span><span class=v id=oi2>—</span></div>
   <div class=liqrow><span class=k>Retail · ritel</span><span class=v id=ls2>—</span></div>
   <div class=liqbar style="margin:2px 0 7px"><div class=b id=lsL style="flex:1">—</div><div class=a id=lsS style="flex:1">—</div></div>
   <div class=liqrow><span class=k>Whale · top trader</span><span class=v id=top2>—</span></div>
   <div class=liqbar style="margin:2px 0 7px"><div class=b id=topL style="flex:1">—</div><div class=a id=topS style="flex:1">—</div></div>
   <div class=liqrow><span class=k>Taker · agresif</span><span class=v id=taker2>—</span></div>
   <div class=liqbar style="margin:2px 0 2px"><div class=b id=tkB style="flex:1">—</div><div class=a id=tkS style="flex:1">—</div></div>
  </section>
  <div class="rv d3" style="display:flex;flex-direction:column;gap:10px">
  <section class="panel">
   <div class=panel-h><span class=t><span class=sq></span>24h Statistics</span></div>
   <div class=statg>
    <div class=s><div class=k>24h High</div><div class=v id=hi>—</div></div>
    <div class=s><div class=k>24h Low</div><div class=v id=lo>—</div></div>
    <div class=s><div class=k>24h Volume</div><div class=v id=vol>—</div></div>
    <div class=s><div class=k>24h Change</div><div class=v id=ch24>—</div></div>
   </div>
  </section>
  <section class="panel rv d4">
   <div class=panel-h><span class=t><span class=sq></span>Market Snapshot</span></div>
   <div class=liqrow><span class=k>Mark Price</span><span class=v id=mk2>—</span></div>
   <div class=liqrow><span class=k>Funding 8h</span><span class=v id=fnd2>—</span></div>
   <div class=liqrow><span class=k>Weighted Avg</span><span class=v id=wavg>—</span></div>
   <div class=liqrow><span class=k>Trades 24h</span><span class=v id=trades>—</span></div>
   <div class=liqrow><span class=k>Total Mcap</span><span class=v id=mcap>—</span></div>
   <div class=liqrow><span class=k>Mcap 24h</span><span class=v id=mcapch>—</span></div>
  </section>
  </div>
  <section class="panel span2 rv d5">
   <div class=panel-h><span class=t><span class=sq></span>AI Read · Gemini</span><span id=aibias class=aibias>—</span></div>
   <div id=aibody class=aibody><div style="color:var(--dim);font-size:12px">memuat…</div></div>
  </section>
  <section class="panel span2 rv d5" id=fedLivePanel style="display:none">
   <div class=panel-h><span class=t><span class=sq></span>🔴 Fed Live · YouTube</span><span id=fedLiveWhen style="font-size:11px;color:var(--down)">—</span></div>
   <div style="position:relative;padding-bottom:56.25%;height:0;border-radius:6px;overflow:hidden;background:#000">
    <iframe id=fedLiveFrame style="position:absolute;top:0;left:0;width:100%;height:100%;border:0" allow="autoplay; encrypted-media" allowfullscreen></iframe>
   </div>
   <div style="font-size:10.5px;color:var(--dim);line-height:1.55;margin-top:7px">Teks Inggris otomatis: klik ⚙️ di player → Subtitles/CC → Auto-translate → Indonesian (kualitas auto-translate YouTube, bukan buatan sendiri).</div>
  </section>
  <section class="panel span2 rv d5">
   <div class=panel-h><span class=t><span class=sq></span>US Dollar Index · DXY</span><span id=dxyChg style="font-size:11px;color:var(--dim)">—</span></div>
   <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:4px"><b id=dxyVal style="font-family:var(--mono);font-size:22px">—</b><span id=dxy30 style="font-size:11px;color:var(--dim)"></span></div>
   <div id=dxyChart style="height:120px"></div>
   <div id=dxyNote style="font-size:10.5px;color:var(--dim);line-height:1.55;margin-top:6px">memuat…</div>
  </section>
  <section class="panel span2 rv d3">
   <div class=panel-h><span class=t><span class=sq></span>Kalender Ekonomi US</span><span id=calwarn style="font-size:11px;color:var(--dim)">—</span></div>
   <div style="font-size:10.5px;color:var(--dim);padding:0 0 7px;line-height:1.55">🔴 dampak besar · 🟠 sedang · 🟡 kecil — <b>jadwal rilis data AS yang bisa bikin harga BTC gerak kencang</b>. Jam = WIB. Tiap event ada penjelasan singkat + arah efeknya.</div>
   <div id=calbody class=wire><div style="color:var(--dim);font-size:12px">memuat…</div></div>
  </section>
  <section class="panel span2 rv d3">
   <div class=panel-h><span class=t><span class=sq></span>🌍 Berita Makro/Geopolitik</span><span id=macrowarn style="font-size:11px;color:var(--dim)">—</span></div>
   <div style="font-size:10.5px;color:var(--dim);padding:0 0 7px;line-height:1.55">Perang, sanksi, krisis pasokan minyak (mis. Selat Hormuz) dll — event non-jadwal yang bisa gerakin market tiba-tiba.</div>
   <div id=macrobody class=wire><div style="color:var(--dim);font-size:12px">memuat…</div></div>
  </section>
  <section class="panel span2 rv d5">
   <div class=panel-h><span class=t><span class=sq></span><span id=newstitle>News — BTC</span></span><button id=trBtn class=trbtn title="Terjemahkan ke Indonesia">ID</button></div>
   <div id=newsSum class=newssum></div>
   <div class=wire id=news></div>
  </section>
 </div>
 <footer class=foot><span>Crypto Terminal · public</span><span>IBM Plex Mono · Bricolage Grotesque</span><span id=ts>—</span></footer>
</div>
<script>
const $=id=>document.getElementById(id);let chart,candleS,lineS,volS,rsiChart,rsiS,curTF='15m',cty='candle',sym='BTCUSDT',lastPx=0,chartReady=false,boxes,liq,liqz,liqOn=false,liqRealOn=false,sigOn=false,newsLang='',cur='USD',fxRate=16000,wall,obp,wallOn=false,obpOn=false,snr,snrOn=false,replayOn=false,rpIdx=0,rpPlaying=false,rpTimer=null,rpSpeed=2;
// ===== INDIKATOR (TradingView-style, dihitung CLIENT-SIDE dari klines -> NOL beban server, aman 100+ user) =====
let SUBCH=[],_syncing=false,CBASE=null,macdChart,macdHist,macdLine,macdSig,stochChart,stochK,stochD;
const ovl={};   // overlay line series (EMA/SMA/BB/Ichimoku) di chart utama, lazy
const IND={ema:{on:false,p:20},sma:{on:false,p:50},bb:{on:false,p:20,k:2},ichi:{on:false},rsi:{on:true,p:14},vol:{on:true},macd:{on:false,f:12,s:26,sig:9},stoch:{on:false,k:14,d:3}};
const TFS={'1m':60,'3m':180,'5m':300,'15m':900,'1h':3600,'4h':14400,'1d':86400};
function snap(t,tf){const s=TFS[tf]||900;return Math.floor(t/s)*s;}
function setView(bars,keep){const n=bars.length;const r={from:bars[Math.max(0,n-keep)].time,to:bars[n-1].time};setTimeout(()=>{try{chart.timeScale().setVisibleRange(r);}catch(e){}},60);}
function fitView(){setTimeout(()=>{try{chart.timeScale().fitContent();}catch(e){}},60);}   // anchor candle fit (deferred -> reliable abis switch/layout)
function rsiSet(arr){const cl=arr.map(k=>k.close);const r=RSI(cl,IND.rsi.p);rsiS.setData(arr.map((k,i)=>r[i]!=null?{time:k.time,value:+r[i].toFixed(2)}:{time:k.time}));}  // whitespace {time} utk bar awal null -> index sejajar candle (RSI ga mundur)
class TradeBoxes{ // primitive lightweight-charts: zona hijau(entry->TP)+merah(entry->SL) per trade, TradingView-style
 constructor(){this._t=[];this._u=null;}
 attached(p){this._u=p.requestUpdate;} detached(){this._u=null;}
 set(t){this._t=t||[];if(this._u)this._u();}
 updateAllViews(){} paneViews(){return [this];} zOrder(){return 'bottom';} renderer(){return this;}
 draw(target){const t=this._t,ts=chart.timeScale();target.useBitmapCoordinateSpace(s=>{const ctx=s.context,hr=s.horizontalPixelRatio,vr=s.verticalPixelRatio;
  t.forEach(o=>{let x1=ts.timeToCoordinate(o.et),x2=ts.timeToCoordinate(o.xt);if(x1==null||x2==null)return;if(x2<=x1)x2=x1+8;
   const ye=candleS.priceToCoordinate(o.entry),yt=candleS.priceToCoordinate(o.tp),ysl=candleS.priceToCoordinate(o.sl);if(ye==null)return;
   const X1=x1*hr,W=(x2-x1)*hr,Ye=ye*vr;
   if(yt!=null){ctx.fillStyle='rgba(39,208,122,0.13)';ctx.fillRect(X1,Math.min(Ye,yt*vr),W,Math.abs(yt*vr-Ye));}
   if(ysl!=null){ctx.fillStyle='rgba(255,69,58,0.13)';ctx.fillRect(X1,Math.min(Ye,ysl*vr),W,Math.abs(ysl*vr-Ye));}
   ctx.lineWidth=Math.max(1,hr);
   ctx.strokeStyle='rgba(255,180,84,0.9)';ctx.beginPath();ctx.moveTo(X1,Ye);ctx.lineTo(X1+W,Ye);ctx.stroke();
   if(yt!=null){ctx.strokeStyle='rgba(39,208,122,0.85)';ctx.beginPath();ctx.moveTo(X1,yt*vr);ctx.lineTo(X1+W,yt*vr);ctx.stroke();}
   if(ysl!=null){ctx.strokeStyle='rgba(255,69,58,0.85)';ctx.beginPath();ctx.moveTo(X1,ysl*vr);ctx.lineTo(X1+W,ysl*vr);ctx.stroke();}
  });});}
}
class LiqMap{ // primitive: pita horizontal heat di level liq leverage-tier (ESTIMASI). hijau=long-liq(bawah), merah=short-liq(atas)
 constructor(){this._b=[];this._bw=0;this._u=null;}
 attached(p){this._u=p.requestUpdate;} detached(){this._u=null;}
 set(b,bw){this._b=b||[];this._bw=bw||0;if(this._u)this._u();}
 updateAllViews(){} paneViews(){return [this];} zOrder(){return 'bottom';} renderer(){return this;}
 draw(target){const b=this._b;if(!b.length)return;target.useBitmapCoordinateSpace(s=>{const ctx=s.context,W=s.bitmapSize.width,vr=s.verticalPixelRatio;
  b.forEach(o=>{const yc=candleS.priceToCoordinate(o.price);if(yc==null)return;
   const y1=candleS.priceToCoordinate(o.price+this._bw/2),y2=candleS.priceToCoordinate(o.price-this._bw/2);
   let h=(y1!=null&&y2!=null)?Math.abs(y2-y1)*vr:2*vr;if(h<1.5)h=1.5;
   ctx.fillStyle='rgba('+(o.side=='long'?'39,208,122':'255,69,58')+','+(0.05+o.v*0.42).toFixed(3)+')';
   ctx.fillRect(0,yc*vr-h/2,W,h);});});}
}
class LiqZones{ // garis+label ZONA likuidasi TERKUAT (magnet). hijau bawah=long-liq(area BELI), merah atas=short-liq(area JUAL). #1 tiap sisi = ★ label tebal, sisanya garis tipis putus2.
 constructor(){this._z=[];this._u=null;}
 attached(p){this._u=p.requestUpdate;} detached(){this._u=null;}
 set(z){this._z=z||[];if(this._u)this._u();}
 updateAllViews(){} paneViews(){return [this];} zOrder(){return 'top';} renderer(){return this;}
 draw(target){const z=this._z;if(!z.length)return;target.useBitmapCoordinateSpace(s=>{const ctx=s.context,W=s.bitmapSize.width,H=s.mediaSize.height,hr=s.horizontalPixelRatio,vr=s.verticalPixelRatio;
  const topP=candleS.coordinateToPrice(0),botP=candleS.coordinateToPrice(H);
  z.forEach(o=>{const strong=o.rank===0,col=o.side=='long'?'39,208,122':'255,69,58';
   let yc=candleS.priceToCoordinate(o.price),pin=0;
   if(yc==null||yc<1||yc>H-1){if(topP!=null&&o.price>topP)pin=1;else if(botP!=null&&o.price<botP)pin=-1;else return;yc=pin>0?1:H-1;}   // zona di luar layar -> pin label ke tepi (atas/bawah) biar ga "hilang" pas di-geser
   if(!strong&&pin)return;   // garis tipis non-★ ga dipaksa kalau keluar layar
   const y=yc*vr;
   if(!pin){ctx.strokeStyle='rgba('+col+','+(strong?0.95:0.40)+')';ctx.lineWidth=Math.max(1,(strong?2:1)*hr);if(!strong)ctx.setLineDash([6*hr,5*hr]);ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke();ctx.setLineDash([]);}
   if(!strong)return;   // cuma zona TERKUAT (★) yg dilabel; rank1/2 = garis tipis konteks
   const tag=(pin>0?'▲ ':pin<0?'▼ ':'★ ')+(o.side=='long'?'LONG-LIQ ':'SHORT-LIQ ')+fp(o.price);
   ctx.font='bold '+(10.5*hr)+'px monospace';const tw=ctx.measureText(tag).width,rx=W-tw-12*hr;   // label di KANAN (dekat axis) -> ga ketutup kotak legend kiri
   const ty=pin>0?10*hr:pin<0?H*vr-10*hr:y;   // kalau ke-pin, label nempel tepi atas/bawah
   ctx.fillStyle='rgba('+col+',0.96)';ctx.fillRect(rx-5*hr,ty-8.5*hr,tw+9*hr,17*hr);
   ctx.fillStyle='#0a0700';ctx.textAlign='left';ctx.textBaseline='middle';ctx.fillText(tag,rx,ty);});});}
}
class WallLines{ // tembok orderbook ASLI (limit gede) = S/R. ijo=bid(support bawah), merah=ask(resist atas). tebal = gede.
 constructor(){this._w=[];this._u=null;}
 attached(p){this._u=p.requestUpdate;} detached(){this._u=null;}
 set(w){this._w=w||[];if(this._u)this._u();}
 updateAllViews(){} paneViews(){return [this];} zOrder(){return 'bottom';} renderer(){return this;}
 draw(target){const w=this._w;if(!w.length)return;target.useBitmapCoordinateSpace(s=>{const ctx=s.context,W=s.bitmapSize.width,hr=s.horizontalPixelRatio,vr=s.verticalPixelRatio;
  w.forEach(o=>{const yc=candleS.priceToCoordinate(o.price);if(yc==null)return;const y=yc*vr,col=o.side=='bid'?'39,208,122':'255,69,58';
   ctx.strokeStyle='rgba('+col+','+(0.4+o.v*0.55).toFixed(3)+')';ctx.lineWidth=Math.max(1.5,(1.5+o.v*3)*hr);
   ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke();
   const q=(o.qty>=1000?(o.qty/1000).toFixed(1)+'K':Math.round(o.qty))+' '+SN[sym];   // tag kanan jelas (canvas -> ga ganggu skala/anchor)
   ctx.font='bold '+(9.5*hr)+'px monospace';const tw=ctx.measureText(q).width;
   ctx.fillStyle='rgba('+col+',0.92)';ctx.fillRect(W-tw-11*hr,y-7*hr,tw+9*hr,14*hr);
   ctx.fillStyle='#0a0700';ctx.textAlign='left';ctx.textBaseline='middle';ctx.fillText(q,W-tw-6*hr,y);});});}
}
class ObProfile{ // profil ORDER BOOK (resting liquidity, akumulasi waktu) di sisi KANAN chart. hijau=bid(beli/support), merah=ask(jual/resist). panjang bar = makin byk order nongkrong.
 constructor(){this._b=[];this._bw=0;this._u=null;}
 attached(p){this._u=p.requestUpdate;} detached(){this._u=null;}
 set(b,bw){this._b=b||[];this._bw=bw||0;if(this._u)this._u();}
 updateAllViews(){} paneViews(){return [this];} zOrder(){return 'top';} renderer(){return this;}
 draw(target){const b=this._b;if(!b.length)return;target.useBitmapCoordinateSpace(s=>{const ctx=s.context,W=s.bitmapSize.width,vr=s.verticalPixelRatio;
  const maxLen=W*0.22;
  b.forEach(o=>{const yc=candleS.priceToCoordinate(o.price);if(yc==null)return;
   const y1=candleS.priceToCoordinate(o.price+this._bw/2),y2=candleS.priceToCoordinate(o.price-this._bw/2);
   let h=(y1!=null&&y2!=null)?Math.abs(y2-y1)*vr:3*vr;if(h<2)h=2;h*=0.85;
   const len=maxLen*o.v,col=o.side=='bid'?'39,208,122':'255,69,58';
   ctx.fillStyle='rgba('+col+','+(0.16+o.v*0.5).toFixed(3)+')';
   ctx.fillRect(W-len,yc*vr-h/2,len,h);});});}
}
class SnrLines{ // S/R AUTO dari pivot price-action. ijo=support(bawah), merah=resist(atas). garis putus2, label N× = jumlah touch.
 constructor(){this._s=[];this._u=null;}
 attached(p){this._u=p.requestUpdate;} detached(){this._u=null;}
 set(s){this._s=s||[];if(this._u)this._u();}
 updateAllViews(){} paneViews(){return [this];} zOrder(){return 'bottom';} renderer(){return this;}
 draw(target){const a=this._s;if(!a.length)return;target.useBitmapCoordinateSpace(s=>{const ctx=s.context,W=s.bitmapSize.width,H=s.mediaSize.height,hr=s.horizontalPixelRatio,vr=s.verticalPixelRatio;
  const topP=candleS.coordinateToPrice(0),botP=candleS.coordinateToPrice(H);
  a.forEach(o=>{let yc=candleS.priceToCoordinate(o.price),pin=0;
   if(yc==null||yc<1||yc>H-1){if(topP!=null&&o.price>topP)pin=1;else if(botP!=null&&o.price<botP)pin=-1;else return;yc=pin>0?1:H-1;}   // level di luar layar -> pin label ke tepi (ga "hilang" pas zoom/pan)
   const col=o.side=='sup'?'39,208,122':'255,69,58';
   if(!pin){const y=yc*vr;ctx.strokeStyle='rgba('+col+','+(0.35+o.v*0.5).toFixed(3)+')';ctx.lineWidth=Math.max(1,(1+o.v*2)*hr);ctx.setLineDash([7*hr,5*hr]);ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke();ctx.setLineDash([]);}
   const lab=(pin>0?'▲ ':pin<0?'▼ ':'')+o.touches+'×'+(pin?' '+Math.round(o.price):'');
   const ty=pin>0?9*hr:pin<0?H*vr-9*hr:yc*vr;
   ctx.font='bold '+(9*hr)+'px monospace';const tw=ctx.measureText(lab).width;
   ctx.fillStyle='rgba('+col+',0.9)';ctx.fillRect(4*hr,ty-7*hr,tw+8*hr,14*hr);
   ctx.fillStyle='#0a0700';ctx.textAlign='left';ctx.textBaseline='middle';ctx.fillText(lab,8*hr,ty);});});}
}
const SN={BTCUSDT:'BTC',ETHUSDT:'ETH',SOLUSDT:'SOL'};
function RSI(c,p){p=p||14;let o=Array(c.length).fill(null),g=0,l=0;for(let i=1;i<=p;i++){const d=c[i]-c[i-1];if(d>=0)g+=d;else l-=d;}g/=p;l/=p;o[p]=100-100/(1+g/(l||1e-9));for(let i=p+1;i<c.length;i++){const d=c[i]-c[i-1];g=(g*(p-1)+(d>0?d:0))/p;l=(l*(p-1)+(d<0?-d:0))/p;o[i]=100-100/(1+g/(l||1e-9));}return o;}
function fmt(n){return n>=1e9?(n/1e9).toFixed(2)+'B':n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':Math.round(n);}
// ----- indikator: hitung array (null = warmup) -----
function EMA(c,p){const o=Array(c.length).fill(null);if(c.length<p)return o;let k=2/(p+1),e=0;for(let i=0;i<p;i++)e+=c[i];e/=p;o[p-1]=e;for(let i=p;i<c.length;i++){e=c[i]*k+e*(1-k);o[i]=e;}return o;}
function SMA(c,p){const o=Array(c.length).fill(null);let s=0;for(let i=0;i<c.length;i++){s+=c[i];if(i>=p)s-=c[i-p];if(i>=p-1)o[i]=s/p;}return o;}
function BB(c,p,k){const m=SMA(c,p),u=Array(c.length).fill(null),lo=Array(c.length).fill(null);for(let i=p-1;i<c.length;i++){let v=0;for(let j=i-p+1;j<=i;j++)v+=(c[j]-m[i])**2;const sd=Math.sqrt(v/p);u[i]=m[i]+k*sd;lo[i]=m[i]-k*sd;}return{mid:m,up:u,lo:lo};}
function MACD(c,f,s,sig){const ef=EMA(c,f),es=EMA(c,s),macd=ef.map((v,i)=>v!=null&&es[i]!=null?v-es[i]:null);
 const signal=Array(c.length).fill(null);let k=2/(sig+1),e=null,sum=0,n=0;
 for(let i=0;i<macd.length;i++){if(macd[i]==null)continue;if(e==null){sum+=macd[i];n++;if(n==sig){e=sum/sig;signal[i]=e;}}else{e=macd[i]*k+e*(1-k);signal[i]=e;}}
 const hist=macd.map((v,i)=>v!=null&&signal[i]!=null?v-signal[i]:null);return{macd,signal,hist};}
function STOCHO(h,l,c,kP,dP){const K=Array(c.length).fill(null);for(let i=kP-1;i<c.length;i++){let hh=-1e18,ll=1e18;for(let j=i-kP+1;j<=i;j++){if(h[j]>hh)hh=h[j];if(l[j]<ll)ll=l[j];}K[i]=hh==ll?50:(c[i]-ll)/(hh-ll)*100;}
 const D=Array(c.length).fill(null);for(let i=kP-1+dP-1;i<c.length;i++){let s=0,ok=true;for(let j=i-dP+1;j<=i;j++){if(K[j]==null){ok=false;break;}s+=K[j];}if(ok)D[i]=s/dP;}return{k:K,d:D};}
function ICHIM(h,l,c){const n=c.length;function dch(p){const o=Array(n).fill(null);for(let i=p-1;i<n;i++){let hh=-1e18,ll=1e18;for(let j=i-p+1;j<=i;j++){if(h[j]>hh)hh=h[j];if(l[j]<ll)ll=l[j];}o[i]=(hh+ll)/2;}return o;}
 const t=dch(9),k=dch(26),b=dch(52),a=t.map((v,i)=>v!=null&&k[i]!=null?(v+k[i])/2:null);return{tenkan:t,kijun:k,spanA:a,spanB:b};}
// ----- indikator: series + pane management -----
function lazyLine(key,opts){if(!ovl[key])ovl[key]=chart.addLineSeries(Object.assign({lineWidth:1.5,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false},opts||{}));return ovl[key];}
function setLine(key,bars,arr,opts){lazyLine(key,opts).setData(bars.map((k,i)=>arr[i]!=null?{time:k.time,value:+arr[i]}:{time:k.time}));}
function clrLine(key){if(ovl[key])ovl[key].setData([]);}
function wireSub(c){SUBCH.push(c);c.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(_syncing||!r)return;_syncing=true;try{chart.timeScale().setVisibleLogicalRange(r);SUBCH.forEach(o=>{if(o!==c)o.timeScale().setVisibleLogicalRange(r);});}catch(e){}_syncing=false;});}
function mkPane(divId){const c=LightweightCharts.createChart($(divId),Object.assign({},CBASE,{timeScale:{visible:false,borderColor:'#1b1810'},rightPriceScale:{borderColor:'#1b1810'}}));wireSub(c);
 setTimeout(()=>{try{const r=chart.timeScale().getVisibleLogicalRange();if(r){_syncing=true;c.timeScale().setVisibleLogicalRange(r);_syncing=false;}}catch(e){}},60);return c;}
function ensureMacd(){if(macdChart)return;macdChart=mkPane('macd');macdHist=macdChart.addHistogramSeries({priceLineVisible:false,lastValueVisible:false});macdLine=macdChart.addLineSeries({color:'#42a5f5',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});macdSig=macdChart.addLineSeries({color:'#ff8c1a',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});}
function ensureStoch(){if(stochChart)return;stochChart=mkPane('stoch');stochK=stochChart.addLineSeries({color:'#42a5f5',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});stochD=stochChart.addLineSeries({color:'#ff8c1a',lineWidth:1,priceLineVisible:false,lastValueVisible:false,crosshairMarkerVisible:false});stochK.createPriceLine({price:80,color:'rgba(255,69,58,.4)',lineStyle:2,lineWidth:1});stochK.createPriceLine({price:20,color:'rgba(39,208,122,.4)',lineStyle:2,lineWidth:1});}
function paneShow(name,on){const d=$(name),l=$(name+'Lbl');if(d)d.style.display=on?'block':'none';if(l)l.style.display=on?'block':'none';}
function resizePanes(){[['rsi',rsiChart],['macd',macdChart],['stoch',stochChart]].forEach(a=>{const e=$(a[0]),c=a[1];if(c&&e&&e.style.display!=='none'&&e.clientWidth)c.applyOptions({width:e.clientWidth,height:e.clientHeight});});}
function applyIndicators(bars){if(!bars||!bars.length||!chart)return;
 const cl=bars.map(k=>k.close),hi=bars.map(k=>k.high),lo=bars.map(k=>k.low);
 if(IND.ema.on)setLine('ema',bars,EMA(cl,IND.ema.p),{color:'#26c6da'});else clrLine('ema');
 if(IND.sma.on)setLine('sma',bars,SMA(cl,IND.sma.p),{color:'#ab47bc'});else clrLine('sma');
 if(IND.bb.on){const b=BB(cl,IND.bb.p,IND.bb.k);setLine('bbU',bars,b.up,{color:'rgba(255,167,38,.75)',lineWidth:1});setLine('bbM',bars,b.mid,{color:'rgba(255,167,38,.4)',lineWidth:1,lineStyle:2});setLine('bbL',bars,b.lo,{color:'rgba(255,167,38,.75)',lineWidth:1});}else{clrLine('bbU');clrLine('bbM');clrLine('bbL');}
 if(IND.ichi.on){const c=ICHIM(hi,lo,cl);setLine('ichiT',bars,c.tenkan,{color:'#42a5f5',lineWidth:1});setLine('ichiK',bars,c.kijun,{color:'#ef5350',lineWidth:1});setLine('ichiA',bars,c.spanA,{color:'rgba(39,208,122,.65)',lineWidth:1});setLine('ichiB',bars,c.spanB,{color:'rgba(255,69,58,.55)',lineWidth:1});}else{clrLine('ichiT');clrLine('ichiK');clrLine('ichiA');clrLine('ichiB');}
 if(volS)volS.applyOptions({visible:IND.vol.on});
 paneShow('rsi',IND.rsi.on);
 if(IND.macd.on){ensureMacd();const m=MACD(cl,IND.macd.f,IND.macd.s,IND.macd.sig);
  macdHist.setData(bars.map((k,i)=>m.hist[i]!=null?{time:k.time,value:+m.hist[i],color:m.hist[i]>=0?'rgba(39,208,122,.5)':'rgba(255,69,58,.5)'}:{time:k.time}));
  macdLine.setData(bars.map((k,i)=>m.macd[i]!=null?{time:k.time,value:+m.macd[i]}:{time:k.time}));
  macdSig.setData(bars.map((k,i)=>m.signal[i]!=null?{time:k.time,value:+m.signal[i]}:{time:k.time}));
  paneShow('macd',true);}else paneShow('macd',false);
 if(IND.stoch.on){ensureStoch();const st=STOCHO(hi,lo,cl,IND.stoch.k,IND.stoch.d);
  stochK.setData(bars.map((k,i)=>st.k[i]!=null?{time:k.time,value:+st.k[i]}:{time:k.time}));
  stochD.setData(bars.map((k,i)=>st.d[i]!=null?{time:k.time,value:+st.d[i]}:{time:k.time}));
  paneShow('stoch',true);}else paneShow('stoch',false);
 setTimeout(resizePanes,20);}
function curBars(){return replayOn?(window._bars||[]).slice(rpBase,rpIdx+1):(window._bars||[]);}
function repaint(){const b=curBars();if(b.length){applyIndicators(b);rsiSet(b);}updLabels();}
function updLabels(){$('rsiLbl').textContent='RSI · '+IND.rsi.p;$('macdLbl').textContent='MACD · '+IND.macd.f+' '+IND.macd.s+' '+IND.macd.sig;$('stochLbl').textContent='STOCH · '+IND.stoch.k+' '+IND.stoch.d;}
function saveInd(){try{localStorage.setItem('btcind',JSON.stringify(IND));}catch(e){}}
function loadInd(){try{const o=JSON.parse(localStorage.getItem('btcind')||'{}');for(const k in o)if(IND[k])Object.assign(IND[k],o[k]);}catch(e){}
 document.querySelectorAll('#indMenu [data-ind]').forEach(cb=>cb.checked=!!IND[cb.dataset.ind].on);
 document.querySelectorAll('#indMenu [data-p]').forEach(inp=>{const a=inp.dataset.p.split('.');inp.value=IND[a[0]][a[1]];});}
function wireIndMenu(){
 $('indBtn').onclick=e=>{e.stopPropagation();const m=$('indMenu');m.classList.toggle('open');$('indBtn').classList.toggle('act',m.classList.contains('open'));};
 $('indMenu').onclick=e=>e.stopPropagation();
 document.addEventListener('click',()=>$('indMenu').classList.remove('open'));
 document.querySelectorAll('#indMenu [data-ind]').forEach(cb=>cb.onchange=()=>{IND[cb.dataset.ind].on=cb.checked;saveInd();repaint();});
 document.querySelectorAll('#indMenu [data-p]').forEach(inp=>inp.onchange=()=>{const a=inp.dataset.p.split('.'),v=+inp.value;if(v>0){IND[a[0]][a[1]]=v;saveInd();repaint();}});}
function fp(n){if(cur=='IDR'){return 'Rp'+Number(Math.round(n*fxRate)).toLocaleString('id-ID');}const d=n<5?4:n<100?3:1;return '$'+Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});}
function fvol(n){return cur=='IDR'?'Rp'+fmt(n*fxRate):'$'+fmt(n);}
function PF(v){if(cur=='IDR'){const x=v*fxRate;return x>=1e9?'Rp'+(x/1e9).toFixed(2)+'M':x>=1e6?'Rp'+(x/1e6).toFixed(1)+'jt':'Rp'+Math.round(x/1e3)+'rb';}return v<5?v.toFixed(4):v<100?v.toFixed(3):v.toFixed(1);}   // axis chart: USD/IDR (M=miliar,jt,rb)
function initChart(){
 const base={layout:{background:{color:'transparent'},textColor:'#8a7f63',fontFamily:'IBM Plex Mono',fontSize:11},grid:{vertLines:{color:'rgba(255,140,26,.03)'},horzLines:{color:'rgba(255,140,26,.03)'}},timeScale:{timeVisible:true,borderColor:'#1b1810'},rightPriceScale:{borderColor:'#1b1810'},crosshair:{mode:0,vertLine:{color:'#ff8c1a66',labelBackgroundColor:'#ff8c1a'},horzLine:{color:'#ff8c1a66',labelBackgroundColor:'#ff8c1a'}}};
 CBASE=base;
 chart=LightweightCharts.createChart($('chart'),base);
 chart.applyOptions({localization:{priceFormatter:PF}});
 chart.subscribeClick(param=>{if(!replayOn||param.time==null)return;const idx=rpFind(param.time);rpBase=Math.max(0,idx-1500);rpPause();rpSeek(idx);});   // PF cuma main chart, JANGAN rsiChart (RSI 0-100)
 chart.subscribeClick(param=>{   // klik zona LIQ (sintetik) -> tampil asumsi entry+leverage yg menghasilkan level itu
  const tip=$('liqTip'); if(!tip)return;
  if(replayOn||!liqOn||!liq||!param.point){tip.style.display='none';return;}
  const price=candleS.coordinateToPrice(param.point.y); if(price==null){tip.style.display='none';return;}
  const bw=liq._bw||0, tol=Math.max(bw*0.6, price*0.0015);
  let best=null,bd=Infinity;
  (liq._b||[]).forEach(b=>{const d=Math.abs(b.price-price);if(d<=tol&&d<bd){bd=d;best=b;}});
  if(!best||best.entry==null){tip.style.display='none';return;}
  const col=best.side==='long'?'var(--up)':'var(--down)',lbl=best.side==='long'?'LONG':'SHORT';
  tip.innerHTML='<b style="color:'+col+'">'+lbl+' liq ~'+fp(best.price)+'</b><br>asumsi entry ~<b>'+fp(best.entry)+'</b> · leverage <b>'+best.lev+'x</b><br>kekuatan klaster: <b>'+(best.str||'-')+'</b>';
  const cw=$('chart').clientWidth||600; let lx=param.point.x+14; if(lx+190>cw)lx=param.point.x-204;
  tip.style.left=Math.max(4,lx)+'px'; tip.style.top=Math.max(4,param.point.y-8)+'px'; tip.style.display='block';
 });
 candleS=chart.addCandlestickSeries({upColor:'#27d07a',downColor:'#ff453a',borderVisible:false,wickUpColor:'#27d07a',wickDownColor:'#ff453a'});
 lineS=chart.addLineSeries({color:'#ff8c1a',lineWidth:2,visible:false,priceLineVisible:false});
 volS=chart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'vol'});volS.priceScale().applyOptions({scaleMargins:{top:0.84,bottom:0}});
 liq=new LiqMap();candleS.attachPrimitive(liq);liqz=new LiqZones();candleS.attachPrimitive(liqz);wall=new WallLines();candleS.attachPrimitive(wall);obp=new ObProfile();candleS.attachPrimitive(obp);snr=new SnrLines();candleS.attachPrimitive(snr);boxes=new TradeBoxes();candleS.attachPrimitive(boxes);
 rsiChart=LightweightCharts.createChart($('rsi'),Object.assign({},base,{timeScale:{visible:false,borderColor:'#1b1810'}}));
 rsiS=rsiChart.addLineSeries({color:'#ffb454',lineWidth:1.5,priceLineVisible:false});
 rsiS.createPriceLine({price:70,color:'rgba(255,69,58,.4)',lineStyle:2,lineWidth:1});rsiS.createPriceLine({price:30,color:'rgba(39,208,122,.4)',lineStyle:2,lineWidth:1});rsiS.createPriceLine({price:50,color:'rgba(138,127,99,.3)',lineStyle:3,lineWidth:1});
 chart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(_syncing||!r)return;_syncing=true;try{SUBCH.forEach(o=>o.timeScale().setVisibleLogicalRange(r));}catch(e){}_syncing=false;});   // sync hub: main -> semua sub-pane
 wireSub(rsiChart);   // RSI + (lazy) MACD/Stoch ikut zoom/scroll main
 loadInd();wireIndMenu();updLabels();   // pulihkan setting indikator (localStorage) + wiring menu fx
 loadChart();
}
function setPx(c){window._rawPx=c;const e=$('px');e.textContent=fp(c);if(lastPx&&c!==lastPx){e.classList.remove('flash');void e.offsetWidth;e.classList.add('flash')}lastPx=c;}
function setBars(b){candleS.setData(b.map(k=>({time:k.time,open:k.open,high:k.high,low:k.low,close:k.close})));lineS.setData(b.map(k=>({time:k.time,value:k.close})));volS.setData(b.map(k=>({time:k.time,value:k.volume,color:k.close>=k.open?'rgba(39,208,122,.32)':'rgba(255,69,58,.32)'})));window._lastBarT=b.length?b[b.length-1].time:0;window._firstBarT=b.length?b[0].time:0;window._bars=b;applyIndicators(b);}
function applyV20(v){const tf=curTF;const t0=window._firstBarT||0;   // v20 = strategi 15m; di TF lain marker/box di-SNAP ke candle TF
 if(!sigOn){candleS.setMarkers([]);boxes.set([]);}   // visual buy/sell OFF default
 else{const mks=(v.markers||[]).filter(m=>m.time>=t0).map(m=>Object.assign({},m,{time:snap(m.time,tf)})).sort((a,b)=>a.time-b.time);candleS.setMarkers(mks);  // filter >=bar pertama: marker tua jangan numpuk di pojok kiri
  boxes.set((v.trades||[]).filter(o=>o.xt>=t0).map(o=>o.reason=='open'?Object.assign({},o,{et:snap(o.et,tf),xt:snap(Math.floor(Date.now()/1000)+900,tf)}):Object.assign({},o,{et:snap(o.et,tf),xt:snap(o.xt+3*900,tf)})));}  // trade OPEN: box terus nyambung ke "sekarang" (bukan berhenti 45m stlh exit -- belum exit!)
 if(v.stats)$('chtitle').textContent=SN[sym]+' · v20 strategi 15m ('+v.stats.n+' trade · WR '+v.stats.wr+'% · ret +'+Math.round(v.stats.ret)+'% · '+(v.stats.nl||0)+'L/'+(v.stats.ns||0)+'S)';}
const V20EP={BTCUSDT:'/api/btc_v20',ETHUSDT:'/api/eth_v20',SOLUSDT:'/api/sol_v20'};   // tiap ticker punya v20 sendiri (param vol-normalized ETH/SOL, [[btc-multiticker-eth-sol]])
function loadChart(){chartReady=false;const s=sym;   // s = guard: abaikan respons kalau user keburu switch sym
 if(candleS)try{candleS.priceScale().applyOptions({autoScale:true});}catch(e){}   // reset skala harga (user sempat drag axis -> autoScale mati -> nyangkut pas switch)
 const ep=V20EP[sym];
 if(ep){fetch(ep).then(r=>r.json()).then(v=>{if(s!==sym)return;window._v20=v;
  if(curTF=='15m'){if(!v.bars||!v.bars.length)return;setBars(v.bars);rsiSet(v.bars);applyV20(v);setView(v.bars,500);chartReady=true;setPx(v.bars[v.bars.length-1].close);
   fetch('/api/klines?sym='+sym+'&tf=15m').then(r=>r.json()).then(d=>{if(s!==sym)return;const lt=window._lastBarT||0;d.filter(x=>x.time>=lt).forEach(x=>{candleS.update({time:x.time,open:x.open,high:x.high,low:x.low,close:x.close});lineS.update({time:x.time,value:x.close});volS.update({time:x.time,value:x.volume,color:x.close>=x.open?'rgba(39,208,122,.32)':'rgba(255,69,58,.32)'});});if(d.length){window._lastBarT=d[d.length-1].time;setPx(d[d.length-1].close);}}).catch(_=>{});}   // top-up live 15m biar bar terakhir sejajar 1d (json cuma bar closed)
  else{fetch('/api/klines?sym='+sym+'&tf='+curTF).then(r=>r.json()).then(d=>{if(s!==sym||!d.length)return;setBars(d);rsiSet(d);applyV20(v);fitView();chartReady=true;setPx(d[d.length-1].close);});}});
  return;}
 $('chtitle').textContent=SN[sym]+' · Price Action';candleS.setMarkers([]);boxes.set([]);
 fetch('/api/klines?sym='+sym+'&tf='+curTF).then(r=>r.json()).then(d=>{if(s!==sym||!d.length)return;setBars(d);rsiSet(d);fitView();chartReady=true;setPx(d[d.length-1].close);});}
function tickChart(){if(!chartReady||replayOn)return;const s=sym;fetch('/api/klines?sym='+sym+'&tf='+curTF).then(r=>r.json()).then(d=>{if(s!==sym||!d.length)return;
 const lt=window._lastBarT||0;
 const upd=d.filter(x=>x.time>=lt);   // bar terakhir + bar baru: ISI gap kalau data sempat basi (jangan lompat -> bolong)
 try{upd.forEach(x=>{candleS.update({time:x.time,open:x.open,high:x.high,low:x.low,close:x.close});lineS.update({time:x.time,value:x.close});
  volS.update({time:x.time,value:x.volume,color:x.close>=x.open?'rgba(39,208,122,.32)':'rgba(255,69,58,.32)'});});
  const cl=d.map(x=>x.close);const r=RSI(cl,14);const li=r.length-1;if(r[li]!=null)rsiS.update({time:d[li].time,value:+r[li].toFixed(2)});}catch(e){}
 const k=d[d.length-1];window._lastBarT=k.time;
 setPx(k.close);});}   // update() jaga view sendiri -> JANGAN setVisibleRange (dulu maksa balik ke candle pas digeser)
function refreshV20(){const ep=V20EP[sym];if(!ep)return;const s=sym;fetch(ep).then(r=>r.json()).then(v=>{if(s!==sym)return;window._v20=v;applyV20(v);});}
function liqZones(bins,bw){const out=[];['long','short'].forEach(side=>{const a=bins.filter(x=>x.side==side).sort((x,y)=>x.price-y.price);const zs=[];let z=null;a.forEach(x=>{if(z&&(x.price-z.hi)<=Math.max(bw,z.hi*0.005)){z.v+=x.v;z.pw+=x.price*x.v;z.vw+=x.v;z.hi=x.price;}else{z={side,v:x.v,pw:x.price*x.v,vw:x.v,lo:x.price,hi:x.price};zs.push(z);}});zs.forEach(q=>q.price=q.pw/q.vw);zs.sort((p,q)=>q.v-p.v).slice(0,3).forEach((q,i)=>{q.rank=i;out.push(q);});});return out;}   // gabung bins berdekatan (<=0.5%/binw) jadi ZONA, ambil 3 terkuat/sisi (rank0=terkuat=★)
function loadLiqMap(){if(replayOn)return;if(!liqOn||!liq){if(!liqRealOn&&liq)liq.set([],0);if(liqz)liqz.set([]);return;}const s=sym;fetch('/api/liqmap?sym='+sym).then(r=>r.json()).then(d=>{if(!liqOn||s!==sym)return;const bins=d.bins||[];liq.set(bins,d.binw||0);if(liqz)liqz.set([]);
 const tl=bins.filter(x=>x.side=='long').reduce((a,b)=>!a||b.v>a.v?b:a,null),ts=bins.filter(x=>x.side=='short').reduce((a,b)=>!a||b.v>a.v?b:a,null);
 $('liqTopL').textContent=tl?fp(tl.price):'—';$('liqTopS').textContent=ts?fp(ts.price):'—';}).catch(_=>{});}
$('liqBtn').onclick=()=>{liqOn=!liqOn;$('liqTip').style.display='none';$('liqBtn').classList.toggle('act',liqOn);if(liqOn){liqRealOn=false;$('liqRealBtn').classList.remove('act');$('liqTitle').textContent='LIQ';$('liqMode').textContent='*estimasi proyeksi leverage 10–100x, bukan data exchange';}const lg=$('liqLegend');lg.style.display=(liqOn||liqRealOn)?'block':'none';if(liqOn)lg.classList.toggle('open',innerWidth>700);loadLiqMap();};
function loadLiqReal(){if(replayOn)return;if(!liqRealOn||!liq){if(!liqOn&&liq)liq.set([],0);return;}const s=sym;fetch('/api/liqreal?sym='+sym).then(r=>r.json()).then(d=>{if(!liqRealOn||s!==sym)return;const bins=d.bins||[];liq.set(bins,d.binw||0);if(liqz)liqz.set([]);
 const tl=bins.filter(x=>x.side=='long').reduce((a,b)=>!a||b.v>a.v?b:a,null),ts=bins.filter(x=>x.side=='short').reduce((a,b)=>!a||b.v>a.v?b:a,null);
 $('liqTopL').textContent=tl?fp(tl.price):'—';$('liqTopS').textContent=ts?fp(ts.price):'—';}).catch(_=>{});}
$('liqRealBtn').onclick=()=>{liqRealOn=!liqRealOn;$('liqTip').style.display='none';$('liqRealBtn').classList.toggle('act',liqRealOn);if(liqRealOn){liqOn=false;$('liqBtn').classList.remove('act');$('liqTitle').textContent='LIQ NYATA';$('liqMode').textContent='data NYATA · Coinalyze · 30 hari';}const lg=$('liqLegend');lg.style.display=(liqOn||liqRealOn)?'block':'none';if(liqRealOn)lg.classList.toggle('open',innerWidth>700);loadLiqReal();};
function loadWalls(){if(replayOn)return;if(!wallOn||!wall){if(wall)wall.set([]);return;}const s=sym;fetch('/api/walls?sym='+sym).then(r=>r.json()).then(d=>{if(!wallOn||s!==sym)return;wall.set(d.walls||[]);}).catch(_=>{});}
$('wallBtn').onclick=()=>{wallOn=!wallOn;$('wallBtn').classList.toggle('act',wallOn);loadWalls();};
function loadObmap(){if(replayOn)return;if(!obpOn||!obp){if(obp)obp.set([]);return;}const s=sym;fetch('/api/obmap?sym='+sym).then(r=>r.json()).then(d=>{if(!obpOn||s!==sym)return;obp.set(d.bins||[],d.binw||0);}).catch(_=>{});}
$('bookBtn').onclick=()=>{obpOn=!obpOn;$('bookBtn').classList.toggle('act',obpOn);loadObmap();};
function loadSnr(){if(replayOn)return;if(!snrOn||!snr){if(snr)snr.set([]);return;}const s=sym,t=curTF;fetch('/api/snr?sym='+sym+'&tf='+curTF).then(r=>r.json()).then(d=>{if(!snrOn||s!==sym||t!==curTF)return;snr.set(d.snr||[]);}).catch(_=>{});}
$('snrBtn').onclick=()=>{snrOn=!snrOn;$('snrBtn').classList.toggle('act',snrOn);loadSnr();};
// ===== REPLAY (bar-per-bar ala TradingView, client-side dari window._bars) =====
let rpBase=0;
function rpFind(t){const b=window._bars||[];let i=b.findIndex(x=>x.time>=t);return i<0?b.length-1:i;}
function rpSeek(idx){const bars=window._bars||[];if(!bars.length)return;idx=Math.max(rpBase,Math.min(idx,bars.length-1));rpIdx=idx;const view=bars.slice(rpBase,idx+1);
 candleS.setData(view.map(k=>({time:k.time,open:k.open,high:k.high,low:k.low,close:k.close})));lineS.setData(view.map(k=>({time:k.time,value:k.close})));
 volS.setData(view.map(k=>({time:k.time,value:k.volume,color:k.close>=k.open?'rgba(39,208,122,.32)':'rgba(255,69,58,.32)'})));
 const cl=view.map(k=>k.close),r=RSI(cl,IND.rsi.p);rsiS.setData(view.map((k,i)=>r[i]!=null?{time:k.time,value:+r[i].toFixed(2)}:{time:k.time}));applyIndicators(view);
 const k=bars[idx];setPx(k.close);const d=new Date(k.time*1000);$('rpInfo').textContent=d.toISOString().slice(0,16).replace('T',' ')+'  '+(idx-rpBase+1)+'/'+(bars.length-rpBase);}
function rpPause(){rpPlaying=false;$('rpPlay').textContent='▶';if(rpTimer){clearInterval(rpTimer);rpTimer=null;}}
function rpTick(){if(!replayOn||!rpPlaying)return;if(rpIdx>=(window._bars||[]).length-1){rpPause();return;}rpSeek(rpIdx+1);}
function rpPlay(){if(!replayOn)return;if(rpPlaying){rpPause();return;}rpPlaying=true;$('rpPlay').textContent='⏸';rpTimer=setInterval(rpTick,Math.max(60,1000/rpSpeed));}
function rpEnter(){const bars=window._bars||[];if(!bars.length)return;replayOn=true;rpPlaying=false;$('rpBtn').classList.add('act');$('rpBar').style.display='flex';
 candleS.setMarkers([]);boxes.set([]);if(liq)liq.set([],0);if(liqz)liqz.set([]);if(wall)wall.set([]);if(obp)obp.set([]);if(snr)snr.set([]);
 const i0=Math.floor(bars.length*0.7);rpBase=Math.max(0,i0-1500);rpSeek(i0);setTimeout(()=>{try{chart.timeScale().fitContent()}catch(e){}},60);}
function rpExit(){rpPause();replayOn=false;$('rpBtn').classList.remove('act');$('rpBar').style.display='none';
 const bars=window._bars||[];
 if(bars.length){setBars(bars);rsiSet(bars);if(window._v20&&sym=='BTCUSDT')applyV20(window._v20);setView(bars,500);chartReady=true;tickChart();}  // restore INSTAN dari cache + view balik live
 else loadChart();
 loadLiqMap();loadLiqReal();loadWalls();loadObmap();loadSnr();}
$('rpBtn').onclick=()=>{if(replayOn)rpExit();else rpEnter();};
$('rpPlay').onclick=rpPlay;$('rpExit').onclick=rpExit;
$('rpBack').onclick=()=>{rpPause();rpSeek(rpIdx-1);};
$('rpFwd').onclick=()=>{rpPause();rpSeek(rpIdx+1);};
$('rpSpd').onclick=()=>{const sp=[0.5,1,2,5,10];rpSpeed=sp[(sp.indexOf(rpSpeed)+1)%sp.length];$('rpSpd').textContent=rpSpeed+'×';if(rpPlaying){rpPause();rpPlay();}};
$('ctrlsTgl').onclick=()=>document.querySelector('.ctrls').classList.toggle('min');   // minimize/maximize toolbar chart (candle/line/TF/toggles)
function fitChartSize(){const c=$('chart');if(chart&&c&&c.clientWidth)chart.applyOptions({width:c.clientWidth,height:c.clientHeight});resizePanes();}
$('maxBtn').onclick=()=>{const pnl=$('chart').closest('.panel');const on=pnl.classList.toggle('maxi');$('maxBtn').textContent=on?'⤡':'⤢';$('maxBtn').classList.toggle('act',on);const mob=matchMedia('(max-width:640px)').matches;document.body.style.overflow=(on&&!mob)?'hidden':'';if(on&&mob)setTimeout(()=>pnl.scrollIntoView({block:'start'}),20);setTimeout(fitChartSize,60);};   // HP: perbesar inline (bukan fullscreen jebakan)
window.addEventListener('keydown',e=>{if(e.key=='Escape'){const pnl=$('chart').closest('.panel');if(pnl.classList.contains('maxi')){pnl.classList.remove('maxi');$('maxBtn').textContent='⤢';$('maxBtn').classList.remove('act');document.body.style.overflow='';setTimeout(fitChartSize,60);}}});
window.addEventListener('resize',()=>{clearTimeout(window._rsz);window._rsz=setTimeout(fitChartSize,150);});
$('sigBtn').onclick=()=>{sigOn=!sigOn;$('sigBtn').classList.toggle('act',sigOn);if(window._v20)applyV20(window._v20);};
$('trBtn').onclick=()=>{newsLang=newsLang==='id'?'':'id';$('trBtn').classList.toggle('act',newsLang==='id');if(newsLang==='id')$('news')['inner'+'HTML']='<div class=nempty>menerjemahkan…</div>';loadNews();};
function applyCur(){if(window._rawPx)setPx(window._rawPx);loadMetrics();loadStats();loadLiq();loadLiqMap();if(chart)chart.applyOptions({localization:{priceFormatter:PF}});}   // re-render semua harga + axis chart ke currency aktif
$('curBtn').onclick=()=>{cur=cur=='USD'?'IDR':'USD';$('curBtn').textContent=cur;$('curBtn').classList.toggle('act',cur=='IDR');applyCur();};
fetch('/api/fx').then(r=>r.json()).then(d=>{if(d&&d.idr)fxRate=d.idr;if(cur=='IDR')applyCur();}).catch(_=>{});
$('typeSeg').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('typeSeg').querySelectorAll('button').forEach(x=>x.classList.remove('act'));b.classList.add('act');cty=b.dataset.ty;candleS.applyOptions({visible:cty=='candle'});lineS.applyOptions({visible:cty=='line'});});
$('tfSeg').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('tfSeg').querySelectorAll('button').forEach(x=>x.classList.remove('act'));b.classList.add('act');curTF=b.dataset.tf;loadChart();loadSnr();});
$('symSeg').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('symSeg').querySelectorAll('button').forEach(x=>x.classList.remove('act'));b.classList.add('act');sym=b.dataset.s;lastPx=0;$('chtitle').textContent=SN[sym]+' · Price Action';$('newstitle').textContent='News Wire — '+SN[sym];loadChart();loadMetrics();loadLiq();loadStats();loadNews();loadLiqMap();loadLiqReal();loadWalls();loadObmap();loadSnr();});
let dxyC=null,dxyS=null;
function loadDxy(){fetch('/api/dxy').then(r=>r.json()).then(d=>{const ser=d.series||[];if(!ser.length){$('dxyNote').textContent='data DXY tidak tersedia';return;}
 $('dxyVal').textContent=d.last.toFixed(2);const up=d.chg>=0;
 $('dxyChg').textContent=(up?'▲ +':'▼ ')+d.chg+'% hari ini';$('dxyChg').style.color=up?'var(--up)':'var(--down)';
 $('dxy30').textContent='30 hari: '+(d.chg30>=0?'+':'')+d.chg30+'%';
 $('dxyNote').innerHTML=(d.chg30>=0.3)?'Dollar sedang <b>MENGUAT</b> (DXY naik) → umumnya jadi <b style="color:var(--down)">tekanan buat BTC</b>. Hubungan terbalik, tidak mutlak.':(d.chg30<=-0.3)?'Dollar sedang <b>MELEMAH</b> (DXY turun) → umumnya <b style="color:var(--up)">angin segar buat BTC</b>. Hubungan terbalik, tidak mutlak.':'Dollar relatif <b>DATAR</b> → pengaruh ke BTC kecil. Patokan: DXY naik = BTC tertekan, DXY turun = BTC terangkat.';
 if(!dxyC){dxyC=LightweightCharts.createChart($('dxyChart'),{layout:{background:{color:'transparent'},textColor:'#8a7f63',fontFamily:'IBM Plex Mono',fontSize:10},grid:{vertLines:{visible:false},horzLines:{color:'rgba(255,140,26,.03)'}},timeScale:{timeVisible:false,borderColor:'#1b1810'},rightPriceScale:{borderColor:'#1b1810'},handleScroll:false,handleScale:false});dxyS=dxyC.addAreaSeries({lineColor:'#7aa2ff',topColor:'rgba(122,162,255,.22)',bottomColor:'rgba(122,162,255,.02)',lineWidth:2,priceLineVisible:false});const rs=()=>dxyC.applyOptions({width:$('dxyChart').clientWidth,height:120});rs();new ResizeObserver(rs).observe($('dxyChart'));}
 dxyS.setData(ser.map(e=>({time:e[0],value:e[1]})));dxyC.timeScale().fitContent();});}
function calCoverable(t){t=(t||'').toLowerCase();  // indikator yg ada sumber actual gratis (BLS ATAU ADP-news)
 if(t.indexOf('adp')>=0)return true;  // ADP = beda sumber (Google News rilis-pers ADP), bukan BLS, tapi tetap ke-cover
 return /cpi|consumer price|unemployment rate|non-?farm|nfp|average hourly earnings|ppi|producer price|jolts|job openings/.test(t);}
const _UP='BTC cenderung <b style="color:var(--up)">NAIK</b>',_DN='BTC cenderung <b style="color:var(--down)">TURUN</b>',_MIX='<b style="color:var(--amber2)">bisa liar 2 arah</b>';
function calExplain(t){t=(t||'').toLowerCase();
 // INFLASI: angka lebih tinggi = panas = bunga tinggi = BTC turun
 if(/cpi|consumer price|inflation/.test(t))return{what:'CPI = kenaikan harga barang sehari-hari di AS (inflasi).',atas:'inflasi lebih panas → bunga cenderung tinggi → '+_DN,bawah:'inflasi melandai → bunga bisa turun → '+_UP};
 if(/\bpce\b/.test(t))return{what:'PCE = ukuran inflasi yang paling dipantau The Fed.',atas:'inflasi lebih panas → '+_DN,bawah:'inflasi melandai → '+_UP};
 if(/ppi|producer price/.test(t))return{what:'PPI = harga di tingkat produsen (sinyal awal inflasi).',atas:'tekanan harga naik → '+_DN,bawah:'tekanan harga reda → '+_UP};
 // KERJA KUAT = hawkish = BTC turun
 if(/non-?farm|nfp|payroll/.test(t)&&!/adp/.test(t))return{what:'NFP = lapangan kerja baru AS bulan lalu.',atas:'kerja lebih kuat → bunga bisa naik → '+_DN,bawah:'kerja melemah → bunga bisa turun → '+_UP+' (asal ga anjlok parah)'};
 if(/adp/.test(t))return{what:'ADP = lapangan kerja swasta AS (pemanasan sebelum NFP).',atas:'kerja lebih kuat → '+_DN,bawah:'kerja melemah → '+_UP};
 if(/average hourly earnings|hourly earnings/.test(t))return{what:'Upah per jam — komponen inflasi dari sisi gaji.',atas:'upah naik cepat → inflasi → '+_DN,bawah:'upah melambat → '+_UP};
 if(/jolts|job openings/.test(t))return{what:'JOLTS = jumlah lowongan kerja terbuka di AS.',atas:'lowongan banyak → kerja kuat → '+_DN,bawah:'lowongan sedikit → kerja lemah → '+_UP};
 // KEBALIK: angka TINGGI = ekonomi LEMAH = dovish = BTC naik
 if(/unemployment rate/.test(t))return{what:'Tingkat pengangguran AS. (kebalik: angka naik = ekonomi lemah)',atas:'pengangguran NAIK → ekonomi lemah → bunga bisa turun → '+_UP,bawah:'pengangguran turun → ekonomi kuat → '+_DN};
 if(/unemployment claims|jobless/.test(t))return{what:'Klaim tunjangan pengangguran mingguan. (kebalik)',atas:'klaim NAIK → kerja melemah → '+_UP,bawah:'klaim turun → kerja kuat → '+_DN};
 // FED
 if(/fomc|federal funds|fed chair|powell|warsh|minutes|interest rate/.test(t))return{what:'Keputusan/omongan The Fed soal suku bunga.',atas:'nada "ketat" / bunga naik-ditahan → '+_DN,bawah:'nada "longgar" / bunga turun → '+_UP};
 // AMBIGU (kekuatan ekonomi, 2 arah)
 if(/retail sales/.test(t))return{what:'Retail Sales = belanja masyarakat AS.',atas:'belanja kuat → ekonomi panas → '+_MIX+' (bisa turun krn takut bunga)',bawah:'belanja lemah → '+_MIX};
 if(/ism|pmi/.test(t))return{what:'ISM/PMI = kesehatan industri AS (>50 = ekspansi).',atas:'ekonomi lebih kuat → '+_MIX,bawah:'ekonomi melemah → '+_MIX};
 if(/\bgdp\b/.test(t))return{what:'GDP = pertumbuhan ekonomi AS.',atas:'ekonomi kuat → '+_MIX,bawah:'ekonomi lemah → '+_MIX};
 return{what:'Rilis data ekonomi AS.',atas:'hasil > perkiraan → '+_MIX,bawah:'hasil < perkiraan → '+_MIX};}
let _fedVid='';
function loadFedLive(){fetch('/api/fedlive').then(r=>r.json()).then(d=>{   // MANUAL: admin yg tempel video pas beneran ada siaran (bukan auto-tebak channel)
 const panel=$('fedLivePanel'); if(!panel)return; const vid=d.video_id||'';
 if(vid){ if(_fedVid!==vid){$('fedLiveFrame').src='https://www.youtube.com/embed/'+vid+'?autoplay=0';_fedVid=vid;}
  panel.style.display=''; $('fedLiveWhen').textContent=d.label||'Live sekarang';
 } else { panel.style.display='none'; if(_fedVid){$('fedLiveFrame').src='';_fedVid='';} }
}).catch(_=>{});}
function loadMacroNews(){fetch('/api/macro_news').then(r=>r.json()).then(d=>{const box=$('macrobody');if(!box)return;box.textContent='';
 if(!d||!d.length){$('macrowarn').textContent='tenang';box.innerHTML='<div style="color:var(--dim);font-size:12px">tidak ada berita makro high-impact 48 jam terakhir</div>';return;}
 $('macrowarn').textContent=d.length+' berita';$('macrowarn').style.color='var(--down)';
 d.slice(0,8).forEach(n=>{const row=document.createElement('div');row.className='calrow';
  const hd=document.createElement('div');hd.className='calhd';const ti=document.createElement('a');ti.href=/^https?:\/\//i.test(n.link||'')?n.link:'#';ti.target='_blank';ti.rel='noopener noreferrer';ti.style.color='var(--ink)';ti.style.textDecoration='none';ti.textContent='🔴 '+n.title;hd.appendChild(ti);
  const tm=document.createElement('div');tm.className='calmeta';tm.textContent=n.pub?new Date(n.pub).toLocaleString('id-ID',{timeZone:'Asia/Jakarta',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})+' WIB':'';
  row.appendChild(hd);row.appendChild(tm);box.appendChild(row);});
}).catch(_=>{});}
function loadCalendar(){Promise.all([fetch('/api/calendar').then(r=>r.json()),fetch('/api/fed').then(r=>r.json()).catch(_=>({}))]).then(([d,fed])=>{const ev=d.events||[],now=d.now||Math.floor(Date.now()/1000);
 const up=ev.filter(e=>e.t>now-36*3600).slice(0,14);   // simpan event yg baru rilis (36 jam) biar HASIL keliatan + yang akan datang
 const col=t=>t==3?'var(--down)':t==2?'var(--amber)':'var(--dim)',ic=t=>t==3?'🔴':t==2?'🟠':'🟡';
 const soon=up.find(e=>e.t>now&&e.t-now<7200&&e.tier>=3),w=$('calwarn');
 if(soon){const m=Math.round((soon.t-now)/60);w.textContent='⚠️ '+soon.title+' dlm '+(m>=60?Math.floor(m/60)+'j'+(m%60)+'m':m+'m');w.style.color='var(--down)';}
 else{w.textContent=up.length+' event';w.style.color='var(--dim)';}
 const box=$('calbody');box.textContent='';
 if(!up.length){const z=document.createElement('div');z.style.cssText='color:var(--dim);font-size:12px';z.append('tidak ada event USD high/medium minggu ini · cek: ');
  const mklink0=(href,txt)=>{const a=document.createElement('a');a.href=href;a.target='_blank';a.rel='noopener noreferrer';a.style.cssText='color:var(--amber2);display:inline;text-decoration:underline';a.textContent=txt;return a;};
  z.appendChild(mklink0('https://www.forexfactory.com/calendar','ForexFactory'));box.appendChild(z);return;}
 up.forEach(e=>{const d=new Date(e.t*1000),dt=e.t-now;
  const wib=d.toLocaleString('id-ID',{timeZone:'Asia/Jakarta',weekday:'short',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
  const row=document.createElement('div');row.className='calrow';
  const hd=document.createElement('div');hd.className='calhd';hd.style.cursor='pointer';
  const ti=document.createElement('span');ti.style.color=col(e.tier);ti.textContent=ic(e.tier)+' '+e.title;
  const right=document.createElement('span');right.style.cssText='display:flex;align-items:center;gap:7px;flex:none';
  const tm=document.createElement('span');tm.className='calt';tm.textContent=wib+' WIB';
  const chev=document.createElement('span');chev.textContent='▾';chev.style.cssText='font-size:9px;color:var(--dim);transition:transform .2s,color .2s';
  right.appendChild(tm);right.appendChild(chev);
  hd.appendChild(ti);hd.appendChild(right);
  // detail (meta+hasil+penjelasan) -- SEMUA disembunyikan default di mobile & desktop, cuma judul+jadwal yg keliatan; tap row buat buka
  const det=document.createElement('div');det.className='caldet';
  const meta=document.createElement('div');meta.className='calmeta';
  const ag=-dt;const cd=dt<0?('✓ rilis '+(ag<3600?Math.round(ag/60)+'m lalu':ag<86400?Math.floor(ag/3600)+'j lalu':Math.floor(ag/86400)+'h lalu')):('dlm '+(dt<3600?Math.round(dt/60)+'m':dt<86400?Math.floor(dt/3600)+'j '+Math.round(dt%3600/60)+'m':Math.floor(dt/86400)+'h'));
  meta.append(cd+' · perkiraan: ');const fbb=document.createElement('b');fbb.textContent=e.forecast||'—';meta.appendChild(fbb);meta.append(' · sebelumnya: '+(e.previous||'—'));
  det.appendChild(meta);
  const ex=calExplain(e.title);
  let adir=0;   // arah hasil vs perkiraan: 1=di atas, -1=di bawah, 0=belum/sesuai
  if(e.actual&&e.forecast){const pa=parseFloat(String(e.actual).replace(/[^0-9.\-]/g,'')),pf=parseFloat(String(e.forecast).replace(/[^0-9.\-]/g,''));if(!isNaN(pa)&&!isNaN(pf))adir=pa>pf?1:pa<pf?-1:0;}
  const wt=document.createElement('div');wt.className='calnote';wt.textContent='ℹ️ '+ex.what;
  const upn=document.createElement('div');upn.className='calnote';upn.innerHTML='📈 di atas perkiraan → '+ex.atas;if(adir===-1)upn.style.textDecoration='line-through';
  const dn=document.createElement('div');dn.className='calnote';dn.innerHTML='📉 di bawah perkiraan → '+ex.bawah;if(adir===1)dn.style.textDecoration='line-through';
  if(e.actual){const av=document.createElement('div');av.className='calnote';const cmp=adir===1?' <span style="color:var(--up)">↑ di atas perkiraan</span>':adir===-1?' <span style="color:var(--down)">↓ di bawah perkiraan</span>':(e.forecast?' <span style="color:var(--dim)">= sesuai</span>':'');
   av.innerHTML='✅ <b style="color:var(--amber2)">HASIL: '+e.actual+'</b>'+(e.forecast?' <span style="color:var(--dim)">vs perkiraan '+e.forecast+'</span>':'')+cmp;det.appendChild(av);}
  else if(dt<0){   // udah rilis tapi kita blm punya angkanya (BLS blm update / sumbernya di luar cakupan BLS) -> kasih link eksternal BENERAN, bukan cuma sebut nama situsnya
   const av=document.createElement('div');av.className='calnote';
   av.append((calCoverable(e.title)?'⏳ menunggu hasil (update tiap jam)':'✓ sudah rilis — hasil belum otomatis terbaca')+' · cek: ');
   const mklink=(href,txt)=>{const a=document.createElement('a');a.href=href;a.target='_blank';a.rel='noopener noreferrer';a.style.cssText='color:var(--amber2);display:inline;text-decoration:underline';a.textContent=txt;return a;};
   av.appendChild(mklink('https://www.forexfactory.com/calendar','ForexFactory'));av.append(' · ');av.appendChild(mklink('https://www.investing.com/economic-calendar/','Investing.com'));
   det.appendChild(av);}
  det.appendChild(wt);det.appendChild(upn);det.appendChild(dn);
  if(fed&&fed.active&&e.title===fed.event){   // rangkuman AI Fed (hawkish/dovish + ID) — DOM/textContent (aman XSS)
   const tc=fed.tone==='hawkish'?'var(--down)':fed.tone==='dovish'?'var(--up)':'var(--amber2)';
   const fb=document.createElement('div');fb.className='calnote';fb.style.cssText='margin-top:6px;padding:8px 10px;border:1px solid var(--line);border-left:3px solid '+tc+';border-radius:5px;background:rgba(255,140,26,.03)';
   const h2=document.createElement('div');h2.appendChild(document.createTextNode('🏛️ '));
   const t1=document.createElement('b');t1.textContent='Rangkuman The Fed (AI) ';h2.appendChild(t1);
   const bd=document.createElement('b');bd.textContent=(fed.tone||'').toUpperCase();bd.style.color=tc;h2.appendChild(bd);
   if(fed.tone_id){const ts=document.createElement('span');ts.style.color='var(--dim)';ts.textContent=' — '+fed.tone_id;h2.appendChild(ts);}
   fb.appendChild(h2);
   const ul=document.createElement('ul');ul.style.cssText='margin:5px 0 0;padding-left:16px;line-height:1.55';
   (fed.poin||[]).forEach(p=>{const li=document.createElement('li');li.textContent=p;ul.appendChild(li);});fb.appendChild(ul);
   if(fed.efek_btc){const ef=document.createElement('div');ef.style.cssText='margin-top:4px;color:var(--amber2)';ef.textContent='📊 '+fed.efek_btc;fb.appendChild(ef);}
   det.appendChild(fb);}
  hd.onclick=()=>{const open=det.classList.toggle('open');chev.style.transform=open?'rotate(180deg)':'';chev.style.color=open?'var(--amber)':'var(--dim)';};
  row.appendChild(hd);row.appendChild(det);
  box.appendChild(row);
 });}).catch(_=>{});}
function loadMetrics(){const s=sym;fetch('/api/metrics?sym='+sym).then(r=>r.json()).then(m=>{if(s!==sym)return;const f=$('funding');f.textContent=(m.funding>=0?'+':'')+m.funding.toFixed(4)+'%';f.className='g-v '+(m.funding>=0?'up':'down');$('fnd2').textContent=(m.funding>=0?'+':'')+m.funding.toFixed(4)+'%';$('fng').textContent=m.fng+(m.fng_txt?' · '+m.fng_txt:'');$('fngbar').style.width=(parseInt(m.fng)||0)+'%';$('mark').textContent=fp(m.mark);$('mk2').textContent=fp(m.mark);});}
function agoTxt(ts){if(!ts)return '';const s=Math.max(0,Math.floor(Date.now()/1000)-ts);const m=Math.floor(s/60);const t=m<1?'br saja':(m+'m lalu');return ' <span style="color:var(--faint)" title="data Binance ini publish tiap 5mnt sekali, wajar statis diantaranya">· '+t+'</span>';}
function loadLiq(){const s=sym;fetch('/api/liquidity?sym='+sym).then(r=>r.json()).then(d=>{if(s!==sym)return;if(d.imb!=null){$('lqb').style.flex=d.imb;$('lqa').style.flex=100-d.imb;$('lqb').textContent=Math.round(d.imb)+'% BID';$('lqa').textContent='ASK '+Math.round(100-d.imb)+'%';}if(d.bidWall)$('bidwall').textContent=d.bidWall[1].toFixed(1)+' @ '+fp(d.bidWall[0]);if(d.askWall)$('askwall').textContent=d.askWall[1].toFixed(1)+' @ '+fp(d.askWall[0]);if(d.oi!=null){const v=fmt(d.oi)+' '+SN[sym];$('oi').textContent=v;$('oi2').textContent=v;}const dlt=(cur,prev)=>{if(prev==null)return '';const g=+(cur-prev).toFixed(1);return g>0?' <span style="color:var(--up)">▲'+g+'</span>':g<0?' <span style="color:var(--down)">▼'+Math.abs(g)+'</span>':' <span style="color:var(--dim)">→</span>';};
 if(d.ls_l!=null){$('ls2').innerHTML=d.ls_l+'% long · '+d.ls_s+'% short'+(d.ls_l0!=null?' <span style="color:var(--dim)">(seb '+d.ls_l0+'%)</span>'+dlt(d.ls_l,d.ls_l0):'')+agoTxt(d.ls_ts);$('lsL').style.flex=d.ls_l;$('lsS').style.flex=d.ls_s;$('lsL').textContent=d.ls_l+'%';$('lsS').textContent=d.ls_s+'%';if(d.ls&&$('ls'))$('ls').textContent=d.ls.toFixed(2);}else if(d.ls){const t=d.ls.toFixed(2);if($('ls'))$('ls').textContent=t;$('ls2').textContent=t;}
 if(d.top_l!=null){$('top2').innerHTML=d.top_l+'% long · '+d.top_s+'% short'+(d.top_l0!=null?' <span style="color:var(--dim)">(seb '+d.top_l0+'%)</span>'+dlt(d.top_l,d.top_l0):'')+agoTxt(d.top_ts);$('topL').style.flex=d.top_l;$('topS').style.flex=d.top_s;$('topL').textContent=d.top_l+'%';$('topS').textContent=d.top_s+'%';}else if(d.top)$('top2').textContent=d.top.toFixed(2);
 if(d.tk_b!=null){$('taker2').innerHTML=d.tk_b+'% buy · '+d.tk_s+'% sell'+(d.tk_b0!=null?' <span style="color:var(--dim)">(seb '+d.tk_b0+'%)</span>'+dlt(d.tk_b,d.tk_b0):'')+agoTxt(d.tk_ts);$('tkB').style.flex=d.tk_b;$('tkS').style.flex=d.tk_s;$('tkB').textContent=d.tk_b+'%';$('tkS').textContent=d.tk_s+'%';}else if(d.taker)$('taker2').textContent=d.taker.toFixed(2);});}
function loadStats(){const sy=sym;fetch('/api/stats?sym='+sym).then(r=>r.json()).then(s=>{if(sy!==sym)return;$('hi').textContent=fp(s.high);$('lo').textContent=fp(s.low);$('vol').textContent=fvol(s.quoteVol);const c=$('ch24');c.textContent=(s.change>=0?'+':'')+s.change.toFixed(2)+'%';c.className='v '+(s.change>=0?'up':'down');const g=$('chg');g.textContent=(s.change>=0?'+':'')+s.change.toFixed(2)+'%';g.className=s.change>=0?'up':'down';$('wavg').textContent=fp(s.wavg);$('trades').textContent=fmt(s.trades);});}
const _esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const _safeUrl=u=>/^https?:\/\//i.test(u||'')?u:'#';
function loadNews(){fetch('/api/news?sym='+sym+(newsLang==='id'?'&lang=id':'')).then(r=>r.json()).then(d=>{window._news=d;let h='';
 d.slice(0,8).forEach((n,i)=>{h+='<div class=nitem><div class=nrow onclick="toggleNews('+i+')"><span class=ago>'+_esc(n.ago)+'</span><span class=ttl>'+_esc(n.title)+'<span class=src>'+_esc(n.source)+'</span></span><span class=nchev>▾</span></div>'
  +'<div id=ndet'+i+' class=ndet>'+(n.summary?('<div class=nsum>'+_esc(n.summary)+'</div>'):'<div class=noff>ringkasan tak tersedia.</div>')+'<a href="'+_safeUrl(n.url)+'" target=_blank rel="noopener noreferrer" class=nvisit>Kunjungi berita ↗</a></div></div>';});
 $('news')['inner'+'HTML']=h||'<div class=nempty>no wire</div>';});}
function toggleNews(i){const e=$('ndet'+i);if(!e)return;const r=e.previousElementSibling;e.classList.toggle('open');if(r)r.classList.toggle('open');}
function clock(){const d=new Date();$('fnclock').textContent=d.toUTCString().slice(17,25)+' UTC';$('ts').textContent=d.toUTCString().slice(5,22)+' UTC';}
function loadGlobal(){fetch('/api/global').then(r=>r.json()).then(g=>{if(g.dom){$('dom').textContent=g.dom.toFixed(2)+'%';$('dombar').style.width=g.dom+'%';$('mcap').textContent='$'+g.mcap.toFixed(2)+'T';const c=$('mcapch');c.textContent=(g.mcapch>=0?'+':'')+g.mcapch.toFixed(2)+'%';c.className='v '+(g.mcapch>=0?'up':'down');}});}
function loadAI(){fetch('/api/ai').then(r=>r.json()).then(a=>{const b=$('aibody'),bd=$('aibias');
 if(!a||a.off||!a.commentary){bd.textContent='off';bd.className='aibias';b.innerHTML='<div class=off>AI off — set Gemini key di admin.</div>';return;}
 bd.textContent=a.bias||'netral';bd.className='aibias '+(a.bias||'netral');
 let h='<div class=cm>'+_esc(a.commentary)+'</div>';if(a.whale)h+='<div style="margin-top:9px;padding:8px 10px;border:1px solid var(--line);border-radius:5px;font-size:12px;color:var(--amber2)"><b>Whale:</b> '+_esc(a.whale)+'</div>';
 if(a.whale_ls!=null||a.retail_ls!=null){const c=v=>v>=1?'var(--up)':'var(--down)';h+='<div style="margin-top:7px;display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:var(--dim)">'+
  '<span>whale L/S <b style="color:'+c(a.whale_ls)+'">'+(a.whale_ls!=null?a.whale_ls.toFixed(2):'—')+'</b></span>'+
  '<span>ritel L/S <b style="color:'+c(a.retail_ls)+'">'+(a.retail_ls!=null?a.retail_ls.toFixed(2):'—')+'</b></span>'+
  (a.taker!=null?'<span>taker b/s <b style="color:'+c(a.taker)+'">'+a.taker.toFixed(2)+'</b></span>':'')+'</div>';}
 const ns=$('newsSum');if(ns)ns['inner'+'HTML']=(a.news&&a.news.length)?('<div class=nsumwrap><div class=nsum-h>Ringkasan AI</div><ul class=nsum-list>'+a.news.map(n=>'<li>'+_esc(n)+'</li>').join('')+'</ul></div>'):'';
 const age=a.ts?Math.round((Date.now()/1000-a.ts)/60):'?';h+='<div class=stamp>⟳ '+age+'m lalu · analisa, bukan saran trade</div>';b.innerHTML=h;});}
function loadSignal(){fetch('/api/signal').then(r=>r.json()).then(d=>{const st=$('sigState'),lv=$('sigLvls'),di=$('sigDist');if(!st)return;
 if(d.halted){st.textContent='⛔ HALT';st.style.color='var(--down)';lv.textContent=d.reason||'circuit breaker aktif';di.textContent='';return;}
 const col=d.dir>0?'var(--up)':(d.dir<0?'var(--down)':'var(--dim)');st.textContent=(d.dir>0?'▲ ':(d.dir<0?'▼ ':''))+d.state;st.style.color=col;
 if(d.dir!==0&&d.entry){lv.innerHTML='entry <b>'+fp(d.entry)+'</b> · TP <b style="color:var(--up)">'+fp(d.tp)+'</b> · SL <b style="color:var(--down)">'+fp(d.sl)+'</b>';
  if(d.price){const chg=(d.dir>0?(d.price/d.entry-1):(d.entry/d.price-1))*100;di.innerHTML='harga '+fp(d.price)+' · <b style="color:'+(chg>=0?'var(--up)':'var(--down)')+'">'+(chg>=0?'+':'')+chg.toFixed(2)+'%</b> dari entry';}else di.textContent='';}
 else{lv.textContent='belum ada posisi — nunggu breakout 15m';di.textContent='';}});}
initChart();loadMetrics();loadLiq();loadStats();loadNews();loadCalendar();loadMacroNews();loadGlobal();loadAI();loadDxy();loadFedLive();clock();
(function(){const DEF=[];   // ga ada panel default-tersembunyi (semua tampil); tombol hide/show tetap ada per panel, state disimpan localStorage panelMin
 let sv;try{sv=JSON.parse(localStorage.getItem('panelMin'))||{};}catch(e){sv={};}
 document.querySelectorAll('.panel').forEach(p=>{const h=p.querySelector('.panel-h');if(!h||h.querySelector('.mini'))return;const te=h.querySelector('.t');const ti=te?te.textContent.trim():'';
  const col=(ti in sv)?sv[ti]:DEF.some(d=>ti.includes(d));if(col)p.classList.add('collapsed');
  const m=document.createElement('span');m.className='mini';m.title='sembunyikan / tampilkan';m.textContent=p.classList.contains('collapsed')?'+':'–';
  m.onclick=e=>{e.stopPropagation();p.classList.toggle('collapsed');const c=p.classList.contains('collapsed');m.textContent=c?'+':'–';let s;try{s=JSON.parse(localStorage.getItem('panelMin'))||{};}catch(_){s={};}s[ti]=c;localStorage.setItem('panelMin',JSON.stringify(s));};
  h.appendChild(m);});})();
function loadCompare(){fetch('/api/compare').then(r=>r.json()).then(d=>{
 const b=$('cmpBody'); if(!b)return;
 const syms=['BTCUSDT','ETHUSDT','SOLUSDT']; const g=s=>d[s]||{};
 const row=(label,fn)=>'<tr style="border-bottom:1px solid var(--line)"><td style="padding:7px 8px 7px 0;color:var(--dim)">'+label+'</td>'+syms.map(s=>'<td style="padding:7px 8px">'+fn(g(s))+'</td>').join('')+'</tr>';
 const pxRow=row('Harga',x=>x.mark?fp(x.mark):'—');
 const chgRow=row('24H',x=>x.chg24h==null?'—':'<b style="color:'+(x.chg24h>=0?'var(--up)':'var(--down)')+'">'+(x.chg24h>=0?'+':'')+x.chg24h.toFixed(2)+'%</b>');
 const fundRow=row('Funding 8h',x=>x.funding==null?'—':(x.funding>=0?'+':'')+x.funding.toFixed(4)+'%');
 const retRow=row('v20 Return',x=>x.v20_ret==null?'—':'<b style="color:'+(x.v20_ret>=0?'var(--up)':'var(--down)')+'">'+(x.v20_ret>=0?'+':'')+x.v20_ret+'%</b>');
 const wrRow=row('v20 Win Rate',x=>x.v20_wr==null?'—':x.v20_wr+'%');
 const calRow=row('v20 Calmar',x=>x.v20_cal==null?'—':x.v20_cal);
 const liveRow='<tr><td style="padding:7px 8px 7px 0;color:var(--dim)">Posisi Live</td><td style="padding:7px 8px">'+
  (g('BTCUSDT').live_state?('<b style="color:'+(g('BTCUSDT').live_dir>0?'var(--up)':(g('BTCUSDT').live_dir<0?'var(--down)':'var(--dim)'))+'">'+g('BTCUSDT').live_state+'</b>'):'—')+
  '</td><td style="padding:7px 8px;color:var(--dim);font-size:11px">backtest saja</td><td style="padding:7px 8px;color:var(--dim);font-size:11px">backtest saja</td></tr>';
 b.innerHTML=pxRow+chgRow+fundRow+retRow+wrRow+calRow+liveRow;
}).catch(()=>{});}
function alToast(msg,ok){const t=document.createElement('div');t.style.cssText='position:fixed;top:16px;right:16px;z-index:400;background:rgba(10,9,6,.96);border:1px solid '+(ok?'var(--amber)':'var(--line)')+';border-radius:8px;padding:12px 16px;font-size:12.5px;color:var(--ink);box-shadow:0 12px 34px rgba(0,0,0,.6);max-width:300px;animation:boot .3s ease-out';t.textContent=msg;document.body.appendChild(t);setTimeout(()=>{t.style.transition='opacity .4s';t.style.opacity='0';setTimeout(()=>t.remove(),400);},6000);}
let alAlerts=[];
function loadAlerts(){fetch('/api/alerts').then(r=>r.json()).then(d=>{alAlerts=d.alerts||[];renderAlerts();}).catch(_=>{});}
function renderAlerts(){
 const box=$('alList'); const active=alAlerts.filter(a=>a.active);
 if(!active.length){box.innerHTML='<div style="font-size:11.5px;color:var(--dim)">belum ada alert aktif</div>';return}
 box.innerHTML=active.map(a=>{
  const symN={BTCUSDT:'BTC',ETHUSDT:'ETH',SOLUSDT:'SOL'}[a.sym]||a.sym;
  const label=(a.type==='rsi'?'RSI(15m)':symN+' harga')+' '+(a.op==='<='?'≤':'≥')+' '+a.value;
  return '<div style="display:flex;justify-content:space-between;align-items:center;border:1px solid var(--line);border-radius:6px;padding:8px 11px;font-size:12px">'
   +'<span>🔔 '+_esc(a.type==='rsi'?label:symN+' '+(a.op==='<='?'≤':'≥')+' $'+Number(a.value).toLocaleString())+'</span>'
   +'<button onclick="delAlert(\''+a.id+'\')" style="background:none;border:1px solid var(--line);color:var(--down);border-radius:4px;cursor:pointer;font-size:10px;padding:3px 8px">hapus</button></div>';
 }).join('');
}
function addAlert(){
 const sym=$('alSym').value, type=$('alType').value, op=$('alOp').value, value=$('alVal').value;
 if(!value){$('alMsg').textContent='isi nilai dulu';$('alMsg').style.color='var(--down)';return}
 fetch('/api/alerts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({act:'add',sym,type,op,value})})
  .then(r=>r.json()).then(d=>{
   $('alMsg').textContent=d.ok?'✓ alert dibuat':(d.msg||'gagal');$('alMsg').style.color=d.ok?'var(--up)':'var(--down)';
   if(d.ok){$('alVal').value='';loadAlerts();}
  }).catch(_=>{$('alMsg').textContent='gagal';$('alMsg').style.color='var(--down)'});
}
function delAlert(id){fetch('/api/alerts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({act:'del',id})}).then(_=>loadAlerts());}
function ackAlert(id){fetch('/api/alerts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({act:'ack',id})}).then(_=>loadAlerts());}
function checkAlerts(){
 const active=alAlerts.filter(a=>a.active); if(!active.length)return;
 const bySym={}; active.forEach(a=>{(bySym[a.sym]=bySym[a.sym]||[]).push(a);});
 Object.keys(bySym).forEach(s=>{
  const rules=bySym[s]; const needRsi=rules.some(a=>a.type==='rsi'); const needPrice=rules.some(a=>a.type==='price');
  const symN={BTCUSDT:'BTC',ETHUSDT:'ETH',SOLUSDT:'SOL'}[s]||s;
  const jobs=[];
  if(needPrice) jobs.push(fetch('/api/metrics?sym='+s).then(r=>r.json()).then(m=>({price:m.mark})));
  if(needRsi) jobs.push(fetch('/api/klines?sym='+s+'&tf=15m').then(r=>r.json()).then(bars=>{const c=(bars||[]).map(b=>b.close);const r14=RSI(c,14);return {rsi:r14.length?r14[r14.length-1]:null};}));
  Promise.all(jobs).then(results=>{
   const cur=Object.assign({},...results);
   rules.forEach(a=>{
    const v=a.type==='rsi'?cur.rsi:cur.price; if(v==null)return;
    const hit=a.op==='<='?v<=a.value:v>=a.value;
    if(hit){
     const label=a.type==='rsi'?('RSI(15m) '+v.toFixed(1)):(symN+' harga $'+v.toLocaleString());
     alToast('🔔 '+symN+' alert kena! '+label+' ('+(a.op==='<='?'≤':'≥')+' '+a.value+')',true);
     if(window.Notification&&Notification.permission==='granted') try{new Notification('🔔 '+symN+' alert',{body:label});}catch(e){}
     ackAlert(a.id);
    }
   });
  }).catch(_=>{});
 });
}
if(window.Notification&&Notification.permission==='default'){ /* minta izin notif browser cuma kalau user udah pernah interaksi -> minta pas pertama kali klik halaman */
 document.addEventListener('click',function _once(){Notification.requestPermission();document.removeEventListener('click',_once);},{once:true});
}
loadAlerts();loadCompare();
function poll(fn,ms){setTimeout(function(){fn();setInterval(fn,ms*(0.9+Math.random()*0.2));},Math.random()*ms);}  // jitter: anti cache-stampede 100 user lock-step
setInterval(clock,1000);poll(tickChart,3000);poll(refreshV20,60000);poll(loadMetrics,3000);poll(loadLiq,8000);poll(loadStats,20000);poll(loadNews,300000);poll(loadCalendar,45000);poll(loadMacroNews,180000);poll(loadDxy,300000);poll(loadFedLive,60000);poll(loadGlobal,120000);poll(loadAI,120000);poll(loadLiqMap,60000);poll(loadLiqReal,60000);poll(loadWalls,8000);poll(loadObmap,20000);poll(loadSnr,60000);poll(checkAlerts,15000);poll(loadCompare,20000);
</script></body></html>"""

ADMINP=HEAD+"<title>DNAYAKA · Admin</title></head><body>"+ATMOS+r"""
<div class=wrap style="max-width:560px">
 <header class=hdr><div class=brand><span class=bt style="font-size:15px">⚙</span> DNAYAKA<span style="color:var(--dim);font-weight:400;font-size:11px;letter-spacing:.18em;text-transform:uppercase;margin-left:9px">Admin Panel</span><span class=cur></span></div>
  <div class=r><button class=navtog aria-label=Menu onclick="this.nextElementSibling.classList.toggle('open')">☰</button><div class=navwrap><a class=navlink href="/">CRYPTO</a><a class=navlink href="/logout">LOGOUT</a></div></div></header>
 <section class=hero style="padding:16px 0">
  <div class=label>Status</div><div id=ast class=idx-strip style="margin-top:8px">memuat…</div>
 </section>
 <section class="panel rv d2">
  <div class=panel-h><span class=t><span class=sq></span>Sinyal Saham · Perbarui</span></div>
  <button onclick=refreshStocks() style="width:100%;padding:13px;font-family:var(--mono);font-weight:600;letter-spacing:.1em;text-transform:uppercase;background:transparent;color:var(--amber);border:1px solid var(--amber);border-radius:6px;cursor:pointer;font-size:12px">🔄 Perbarui Sinyal + AI Bandar</button>
  <div id=rmsg style="font-size:11px;color:var(--dim);margin-top:9px;line-height:1.5">fetch data terbaru + sinyal + money-flow + AI bandar (1 batch call). ~5-10 menit.</div>
 </section>
 <section class="panel rv d3">
  <div class=panel-h><span class=t><span class=sq></span>IDX Broker Summary · Cookie (tiap sore)</span></div>
  <p style="font-size:11px;color:var(--dim);line-height:1.5;margin-bottom:8px">Buka IDX broksum di browser (Proton ON) → F12 → Network → GetBrokerSummary → Headers → copy <b>Cookie</b> (ada cf_clearance) + <b>User-Agent</b>. Paste → fetch AK/BK/CC. cf_clearance expired ~30mnt.</p>
  <textarea id=ckck placeholder="Cookie: ...cf_clearance=..." style="width:100%;height:58px;background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:11px;padding:9px;resize:vertical"></textarea>
  <input id=ckua placeholder="User-Agent (persis dari browser)" style="width:100%;margin-top:6px;background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:11px;padding:9px">
  <button onclick=saveCookie() style="width:100%;margin-top:8px;padding:12px;font-family:var(--mono);font-weight:600;letter-spacing:.1em;text-transform:uppercase;background:transparent;color:var(--amber);border:1px solid var(--amber);border-radius:6px;cursor:pointer;font-size:12px">🔓 Simpan & Fetch Broksum</button>
  <div id=ckmsg style="font-size:11px;color:var(--dim);margin-top:8px;line-height:1.5"></div>
 </section>
 <section class="panel rv d3">
  <div class=panel-h><span class=t><span class=sq></span>Keamanan</span></div>
  <p style="font-size:11.5px;color:var(--dim);line-height:1.6">Panel ini AMAN — cuma refresh data (read-only). Kontrol trading (API key, Buy/Sell, live) ada di admin privat <b style="color:var(--amber)">:8789 localhost-only</b>, sengaja TIDAK diekspos ke internet.</p>
 </section>
 <footer class=foot><span>IDX Admin · gated</span><span id=ts>—</span></footer>
</div>
<script>
const $=id=>document.getElementById(id);
function refreshStocks(){$('rmsg').textContent='⟳ menjalankan…';$('rmsg').style.color='var(--amber)';fetch('/api/refresh_stocks',{method:'POST'}).then(r=>r.json()).then(d=>{$('rmsg').textContent=d.msg;$('rmsg').style.color=d.ok?'var(--up)':'var(--down)'}).catch(_=>{$('rmsg').textContent='gagal'})}
function saveCookie(){const c=$('ckck').value.trim().replace(/^Cookie:\s*/i,''),u=$('ckua').value.trim();if(!c){$('ckmsg').textContent='isi cookie dulu';$('ckmsg').style.color='var(--down)';return}$('ckmsg').textContent='⟳ simpan + fetch broksum…';$('ckmsg').style.color='var(--amber)';fetch('/api/idx_cookie',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cookie:c,ua:u})}).then(r=>r.json()).then(d=>{$('ckmsg').textContent=d.msg;$('ckmsg').style.color=d.ok?'var(--up)':'var(--down)';if(d.ok)$('ckck').value=''}).catch(_=>{$('ckmsg').textContent='gagal'})}
function stat(){Promise.all([fetch('/api/ihsg_ta').then(r=>r.json()),fetch('/api/stock_signal').then(r=>r.json())]).then(([t,s])=>{$('ast').innerHTML='<span><span class=k>IHSG</span> <b>'+(t.price||'—')+'</b></span><span><span class=k>Regime</span> <b>'+(t.regime||'-')+'</b></span><span><span class=k>Sinyal beli</span> <b>'+(s.n_buy||0)+'</b></span><span><span class=k>Watchlist</span> <b>'+(s.n_watch||0)+'</b></span><span><span class=k>Update</span> <b>'+(s.ts?new Date(s.ts*1000).toLocaleString():'—')+'</b></span>';}).catch(_=>{});}
function clk(){$('ts').textContent=new Date().toUTCString().slice(5,22)+' UTC'}
stat();clk();setInterval(stat,30000);setInterval(clk,1000);
</script></body></html>"""

JOURNAL=HEAD+"<title>DNAYAKA · Journal</title></head><body>"+ATMOS+r"""
<div class=wrap style="max-width:640px">
 <header class=hdr><div class=brand><span class=bt style="font-size:15px">📓</span> DNAYAKA<span style="color:var(--dim);font-weight:400;font-size:11px;letter-spacing:.18em;text-transform:uppercase;margin-left:9px">Trading Journal</span><span class=cur></span></div>
  <div class=r><button class=navtog aria-label=Menu onclick="this.nextElementSibling.classList.toggle('open')">☰</button><div class=navwrap><a class=navlink href="/">CRYPTO</a><a class=navlink href="/logout">LOGOUT</a></div></div></header>
 <section class="panel rv d1" id=pnlcard style="margin-top:16px;overflow:hidden;position:relative;text-align:center;padding:26px 20px;background:radial-gradient(120% 140% at 50% -20%,rgba(255,140,26,.10),transparent 60%),var(--panel)">
  <div class=label style="letter-spacing:.24em">Total PnL</div>
  <div id=pnlBig class=bigprice style="font-size:clamp(34px,8vw,58px);margin:8px 0 4px">$0.00</div>
  <div id=pnlRow style="display:flex;justify-content:center;gap:22px;flex-wrap:wrap;margin-top:6px;font-size:11.5px;color:var(--dim)">
   <span>Bulan ini <b id=pnlMonth style="color:var(--ink)">$0</b></span>
   <span>Win rate <b id=pnlWR style="color:var(--ink)">—</b></span>
   <span>Trade tercatat <b id=pnlN style="color:var(--ink)">0</b></span>
  </div>
 </section>
 <section class="panel rv d2" style="margin-top:16px">
  <div class=panel-h><span class=t><span class=sq></span><span id=jformtitle>Entri Baru</span></span><span id=jcancelWrap style="display:none"><button onclick=cancelEdit() style="background:none;border:1px solid var(--line);color:var(--dim);border-radius:4px;cursor:pointer;font-size:10px;padding:4px 9px">batal edit</button></span></div>
  <div style="display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap">
   <input id=jsym placeholder="Simbol (opsional, mis. BTC)" style="flex:1;min-width:140px;background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:10px;box-sizing:border-box">
   <input id=jdt type=datetime-local style="flex:1;min-width:180px;background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:10px;box-sizing:border-box;color-scheme:dark">
  </div>
  <div style="display:flex;gap:8px;margin-bottom:8px">
   <button type=button id=jdirL onclick=setDir(1) style="flex:1;padding:9px;border-radius:6px;cursor:pointer;font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:.08em;background:rgba(39,208,122,.14);color:var(--up);border:1px solid var(--up)">▲ LONG</button>
   <button type=button id=jdirS onclick=setDir(-1) style="flex:1;padding:9px;border-radius:6px;cursor:pointer;font-family:var(--mono);font-size:11px;font-weight:600;letter-spacing:.08em;background:transparent;color:var(--dim);border:1px solid var(--line)">▼ SHORT</button>
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px;margin-bottom:6px">
   <input id=jmodal type=number step=any placeholder="Modal $" title="Modal (USD)" oninput=autoPnl() style="background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:10px;box-sizing:border-box">
   <input id=jentry type=number step=any placeholder="Entry $" title="Harga entry" oninput=autoPnl() style="background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:10px;box-sizing:border-box">
   <input id=jexit type=number step=any placeholder="Exit $ (isi utk auto)" title="Harga exit -- isi ini biar PnL kehitung sendiri" oninput=autoPnl() style="background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:10px;box-sizing:border-box">
   <input id=jsl type=number step=any placeholder="SL $ (opsional)" title="Stop loss (opsional)" style="background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:10px;box-sizing:border-box">
   <input id=jlev type=number step=any placeholder="Leverage x" title="Leverage" oninput=autoPnl() style="background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:10px;box-sizing:border-box">
   <input id=jpnl type=number step=any placeholder="PnL $ (auto, bisa edit manual)" title="Otomatis dari Modal/Entry/Exit/Lev — boleh ditimpa manual" style="background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:10px;box-sizing:border-box">
  </div>
  <div id=jpnlHint style="font-size:10.5px;color:var(--dim);margin-bottom:8px;min-height:13px"></div>
  <textarea id=jnote placeholder="Catatan trade — kenapa entry, apa yang dipelajari, dst." style="width:100%;height:90px;background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:12px;padding:10px;resize:vertical;box-sizing:border-box"></textarea>
  <div style="display:flex;align-items:center;gap:10px;margin-top:8px;flex-wrap:wrap">
   <label style="font-size:11px;color:var(--dim);border:1px solid var(--line);border-radius:6px;padding:9px 12px;cursor:pointer">📷 Screenshot<input id=jfile type=file accept="image/png,image/jpeg,image/webp" style="display:none" onchange="onPick(event)"></label>
   <span id=jfname style="font-size:11px;color:var(--dim)"></span>
   <button id=jrmimg onclick=removeImg() style="display:none;background:none;border:1px solid var(--line);color:var(--down);border-radius:4px;cursor:pointer;font-size:10px;padding:5px 9px">hapus gambar lama</button>
  </div>
  <img id=jprev style="display:none;max-width:100%;max-height:220px;border:1px solid var(--line);border-radius:6px;margin-top:8px">
  <button id=jsavebtn onclick=saveEntry() style="width:100%;margin-top:10px;padding:13px;font-family:var(--mono);font-weight:600;letter-spacing:.1em;text-transform:uppercase;background:transparent;color:var(--amber);border:1px solid var(--amber);border-radius:6px;cursor:pointer;font-size:12px">Simpan Entri</button>
  <div id=jmsg style="font-size:11px;color:var(--dim);margin-top:8px"></div>
 </section>
 <section class="panel rv d3" style="margin-top:16px">
  <div class=panel-h><span class=t><span class=sq></span>Kalender PnL</span>
   <span style="display:flex;align-items:center;gap:10px">
    <button onclick="calNav(-1)" style="background:none;border:1px solid var(--line);color:var(--ink);border-radius:4px;cursor:pointer;font-size:12px;padding:3px 9px">‹</button>
    <span id=calLabel style="font-size:11px;color:var(--dim);min-width:96px;text-align:center;letter-spacing:.08em;text-transform:uppercase">—</span>
    <button onclick="calNav(1)" style="background:none;border:1px solid var(--line);color:var(--ink);border-radius:4px;cursor:pointer;font-size:12px;padding:3px 9px">›</button>
   </span>
  </div>
  <div id=calGrid style="display:grid;grid-template-columns:repeat(7,1fr);gap:5px"></div>
  <div style="display:flex;justify-content:center;gap:14px;margin-top:10px;font-size:10px;color:var(--dim)"><span><span style="display:inline-block;width:8px;height:8px;background:var(--up);border-radius:2px;margin-right:4px"></span>profit</span><span><span style="display:inline-block;width:8px;height:8px;background:var(--down);border-radius:2px;margin-right:4px"></span>loss</span><span><span style="display:inline-block;width:8px;height:8px;background:var(--line);border-radius:2px;margin-right:4px"></span>nol/tak ada trade</span></div>
 </section>
 <section class="panel rv d3" style="margin-top:16px">
  <div class=panel-h><span class=t><span class=sq></span>Statistik</span></div>
  <div id=jstats style="font-size:11.5px;color:var(--dim)">belum ada data</div>
 </section>
 <section class="panel rv d3" style="margin-top:16px" id=jlistSec>
  <div class=panel-h><span class=t><span class=sq></span>Riwayat (kamu saja — privat)</span><button onclick=exportCsv() style="background:none;border:1px solid var(--line);color:var(--dim);border-radius:4px;cursor:pointer;font-size:10px;padding:4px 9px">⬇ export CSV</button></div>
  <div id=jlistFilter style="display:none;margin-bottom:9px;padding:7px 10px;background:rgba(255,140,26,.08);border:1px solid var(--amber);border-radius:6px;font-size:11px;color:var(--ink);align-items:center;justify-content:space-between;gap:8px"></div>
  <div id=jlist style="display:flex;flex-direction:column;gap:10px">memuat…</div>
 </section>
 <footer class=foot><span>Journal · privat per-akun</span><span id=ts>—</span></footer>
</div>
<div id=cardModal style="display:none;position:fixed;inset:0;z-index:300;background:rgba(0,0,0,.82);align-items:center;justify-content:center;padding:16px;flex-direction:column;gap:14px">
 <canvas id=shareCanvas style="max-width:100%;max-height:70vh;border-radius:12px;box-shadow:0 30px 80px rgba(0,0,0,.7)"></canvas>
 <div style="display:flex;gap:10px">
  <button onclick=downloadCard() style="padding:11px 20px;font-family:var(--mono);font-weight:600;letter-spacing:.08em;text-transform:uppercase;background:var(--amber);color:#160c00;border:0;border-radius:7px;cursor:pointer;font-size:12px">⬇ Download PNG</button>
  <button onclick=closeCard() style="padding:11px 20px;font-family:var(--mono);font-weight:600;letter-spacing:.08em;text-transform:uppercase;background:transparent;color:var(--dim);border:1px solid var(--line);border-radius:7px;cursor:pointer;font-size:12px">Tutup</button>
 </div>
</div>
<script>
const $=id=>document.getElementById(id);
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c])}
function pad2(n){return String(n).padStart(2,'0')}
function epochToLocalInput(ts){const d=new Date(ts*1000);return d.getFullYear()+'-'+pad2(d.getMonth()+1)+'-'+pad2(d.getDate())+'T'+pad2(d.getHours())+':'+pad2(d.getMinutes())}
function localInputToEpoch(v){const t=new Date(v).getTime();return isFinite(t)?Math.floor(t/1000):0}
let pendingImg=null, editingId=null, removeImgFlag=false, lastEntries=[], compressing=false, curDir=1;
function setDir(d){
 curDir=d;
 $('jdirL').style.background=d===1?'rgba(39,208,122,.14)':'transparent'; $('jdirL').style.color=d===1?'var(--up)':'var(--dim)'; $('jdirL').style.borderColor=d===1?'var(--up)':'var(--line)';
 $('jdirS').style.background=d===-1?'rgba(255,69,58,.14)':'transparent'; $('jdirS').style.color=d===-1?'var(--down)':'var(--dim)'; $('jdirS').style.borderColor=d===-1?'var(--down)':'var(--line)';
 autoPnl();
}
function autoPnl(){
 const modal=parseFloat($('jmodal').value), entry=parseFloat($('jentry').value), exit=parseFloat($('jexit').value), lev=parseFloat($('jlev').value)||1;
 if(!isFinite(modal)||!isFinite(entry)||!isFinite(exit)||entry===0){$('jpnlHint').textContent=$('jexit').value?'':'';return}
 const pnl=modal*lev*((exit-entry)/entry)*curDir;
 $('jpnl').value=Math.round(pnl*100)/100;
 $('jpnlHint').innerHTML='↳ otomatis dari Modal×Lev×perubahan-harga ('+(curDir===1?'LONG':'SHORT')+') — bisa ditimpa manual kalau beda sama exchange';
 $('jpnlHint').style.color='var(--dim)';
}
const _now0=new Date(); let calYear=_now0.getFullYear(), calMonth=_now0.getMonth();
const MONTH_NAMES=['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'];
function fmtMoney(n){const a=Math.abs(n);const s=a>=1000?Number(a.toFixed(0)).toLocaleString():a.toFixed(2);return (n>=0?'+':'-')+'$'+s}
function renderPnlCard(){
 const withPnl=lastEntries.filter(e=>e.pnl!=null);
 const total=withPnl.reduce((a,e)=>a+e.pnl,0);
 const now=new Date(); const thisMonth=withPnl.filter(e=>{const d=new Date(e.ts*1000);return d.getFullYear()===now.getFullYear()&&d.getMonth()===now.getMonth()}).reduce((a,e)=>a+e.pnl,0);
 const wins=withPnl.filter(e=>e.pnl>0).length; const wr=withPnl.length?Math.round(wins/withPnl.length*100):null;
 const col=total>0?'var(--up)':total<0?'var(--down)':'var(--ink)';
 $('pnlBig').textContent=withPnl.length?fmtMoney(total):'$0.00'; $('pnlBig').style.color=col;
 $('pnlBig').style.textShadow=total!==0?('0 0 44px '+(total>0?'rgba(39,208,122,.35)':'rgba(255,69,58,.35)')):'';
 $('pnlMonth').textContent=withPnl.length?fmtMoney(thisMonth):'$0'; $('pnlMonth').style.color=thisMonth>0?'var(--up)':thisMonth<0?'var(--down)':'var(--ink)';
 $('pnlWR').textContent=wr==null?'—':wr+'%'; $('pnlWR').style.color=wr==null?'var(--ink)':(wr>=50?'var(--up)':'var(--down)');
 $('pnlN').textContent=lastEntries.length;
}
function calNav(d){calMonth+=d; if(calMonth<0){calMonth=11;calYear--} else if(calMonth>11){calMonth=0;calYear++} renderCalendar()}
let calFilterDay=null;   // {y,m,d} kalau lagi filter riwayat ke 1 hari (klik kalender), null = tampil semua
function calDayClick(y,m,d){
 if(calFilterDay&&calFilterDay.y===y&&calFilterDay.m===m&&calFilterDay.d===d){calFilterDay=null;}   // klik lagi hari yg sama -> toggle-off
 else{calFilterDay={y,m,d};}
 renderCalendar(); renderList();
 if(calFilterDay) document.getElementById('jlistSec').scrollIntoView({behavior:'smooth',block:'start'});
}
function clearCalFilter(){calFilterDay=null;renderCalendar();renderList();}
function renderCalendar(){
 $('calLabel').textContent=MONTH_NAMES[calMonth]+' '+calYear;
 const byDay={};
 lastEntries.forEach(e=>{
  const d=new Date(e.ts*1000);
  if(d.getFullYear()!==calYear||d.getMonth()!==calMonth) return;
  const key=d.getDate();
  const b=byDay[key]||{pnl:0,n:0,has:false}; b.n++; b.has=true; if(e.pnl!=null)b.pnl+=e.pnl; byDay[key]=b;
 });
 const first=new Date(calYear,calMonth,1); const startDow=first.getDay(); const daysInMonth=new Date(calYear,calMonth+1,0).getDate();
 const todayKey=(new Date()).toDateString();
 let html=['Min','Sen','Sel','Rab','Kam','Jum','Sab'].map(d=>'<div style="text-align:center;font-size:9px;color:var(--dim);letter-spacing:.1em;padding-bottom:4px">'+d+'</div>').join('');
 for(let i=0;i<startDow;i++) html+='<div></div>';
 for(let day=1;day<=daysInMonth;day++){
  const b=byDay[day]; const isToday=new Date(calYear,calMonth,day).toDateString()===todayKey;
  const isSel=calFilterDay&&calFilterDay.y===calYear&&calFilterDay.m===calMonth&&calFilterDay.d===day;
  let bg='var(--bg)', bd='var(--line)', txtcol='var(--dim)';
  if(b&&b.has){ if(b.pnl>0){bg='rgba(39,208,122,.16)';bd='var(--up)'} else if(b.pnl<0){bg='rgba(255,69,58,.16)';bd='var(--down)'} else {bg='rgba(255,140,26,.10)';bd='var(--amber)'} txtcol='var(--ink)' }
  const clickable=b&&b.has;
  html+='<div'+(clickable?(' onclick="calDayClick('+calYear+','+calMonth+','+day+')"'):'')
   +' style="aspect-ratio:1;border:'+(isSel?'2px solid var(--amber)':'1px solid '+(isToday?'var(--amber)':bd))+';background:'+bg+';border-radius:5px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;padding:2px'+(clickable?';cursor:pointer':'')+(isSel?';box-shadow:0 0 0 2px rgba(255,140,26,.25)':'')+'">'
   +'<span style="font-size:10px;color:'+txtcol+'">'+day+'</span>'
   +(b&&b.has?('<span style="font-size:8.5px;font-weight:600;color:'+(b.pnl>0?'var(--up)':b.pnl<0?'var(--down)':'var(--amber)')+'">'+(b.pnl!==0?fmtMoney(b.pnl):b.n+'t')+'</span>'):'')
   +'</div>';
 }
 $('calGrid').innerHTML=html;
}
function roundRect(ctx,x,y,w,h,r){ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath()}
function drawShareCard(e){
 const c=$('shareCanvas'), W=960, H=600, dpr=Math.min(2,window.devicePixelRatio||1);
 c.width=W*dpr; c.height=H*dpr; c.style.width=W+'px'; c.style.height=H+'px';
 const ctx=c.getContext('2d'); ctx.scale(dpr,dpr);
 const up=e.pnl>=0, col=up?'#27d07a':'#ff453a', colGlow=up?'rgba(39,208,122,.28)':'rgba(255,69,58,.28)';
 // bg
 ctx.fillStyle='#040302'; ctx.fillRect(0,0,W,H);
 const rg=ctx.createRadialGradient(W/2,-40,40,W/2,H*0.35,W*0.75);
 rg.addColorStop(0,colGlow); rg.addColorStop(1,'rgba(0,0,0,0)');
 ctx.fillStyle=rg; ctx.fillRect(0,0,W,H);
 // faint grid dots
 ctx.fillStyle='rgba(255,140,26,.05)';
 for(let gx=20;gx<W;gx+=26) for(let gy=20;gy<H;gy+=26) ctx.fillRect(gx,gy,1,1);
 // border
 ctx.strokeStyle='rgba(255,140,26,.35)'; ctx.lineWidth=1.5; roundRect(ctx,10,10,W-20,H-20,16); ctx.stroke();
 // brand row
 ctx.textBaseline='alphabetic';
 ctx.fillStyle='#ff8c1a'; ctx.font='700 20px monospace'; ctx.fillText('₿ DNAYAKA', 44, 62);
 ctx.fillStyle='#8a7f63'; ctx.font='500 12px monospace'; ctx.fillText('TRADING JOURNAL', 44, 80);
 // symbol + dir badge (top right)
 const badge=(e.sym||'TRADE')+'  '+(e.dir===-1?'▼ SHORT':'▲ LONG');
 ctx.textAlign='right'; ctx.font='600 15px monospace'; ctx.fillStyle=e.dir===-1?'#ff453a':'#27d07a';
 ctx.fillText(badge, W-44, 66); ctx.textAlign='left';
 // date
 ctx.fillStyle='#8a7f63'; ctx.font='500 12px monospace'; ctx.textAlign='right';
 ctx.fillText(new Date(e.ts*1000).toLocaleString(), W-44, 84); ctx.textAlign='left';
 // big PnL
 const pnlTxt=(up?'+':'-')+'$'+Math.abs(e.pnl).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
 ctx.textAlign='center'; ctx.fillStyle=col; ctx.font='700 96px monospace';
 ctx.shadowColor=colGlow; ctx.shadowBlur=50;
 ctx.fillText(pnlTxt, W/2, 300); ctx.shadowBlur=0;
 // % return if modal known
 if(e.modal){
  const pct=(e.pnl/e.modal*100); const pctTxt=(pct>=0?'+':'')+pct.toFixed(2)+'% return dari modal';
  ctx.font='500 17px monospace'; ctx.fillStyle='#e8e2d0'; ctx.fillText(pctTxt, W/2, 336);
 }
 ctx.textAlign='left';
 // stat row (entry/exit/lev/modal)
 const stats=[];
 if(e.entry!=null) stats.push(['ENTRY','$'+Number(e.entry).toLocaleString()]);
 if(e.exit!=null) stats.push(['EXIT','$'+Number(e.exit).toLocaleString()]);
 if(e.lev!=null) stats.push(['LEVERAGE',Number(e.lev)+'x']);
 if(e.modal!=null) stats.push(['MODAL','$'+Number(e.modal).toLocaleString()]);
 const n=stats.length||1, colW=(W-88)/n;
 stats.forEach((s,i)=>{
  const cx=44+colW*i;
  ctx.strokeStyle='rgba(255,255,255,.08)'; if(i>0){ctx.beginPath();ctx.moveTo(cx,410);ctx.lineTo(cx,470);ctx.stroke()}
  ctx.fillStyle='#8a7f63'; ctx.font='600 11px monospace'; ctx.fillText(s[0], cx+(i>0?18:0), 430);
  ctx.fillStyle='#e8e2d0'; ctx.font='700 22px monospace'; ctx.fillText(s[1], cx+(i>0?18:0), 460);
 });
 // footer note
 if(e.note){
  ctx.fillStyle='#8a7f63'; ctx.font='italic 13px monospace';
  let note=e.note.length>90?e.note.slice(0,90)+'…':e.note;
  ctx.fillText('"'+note+'"', 44, 520);
 }
 ctx.fillStyle='rgba(255,140,26,.5)'; ctx.font='500 10px monospace'; ctx.textAlign='right';
 ctx.fillText('dnayaka trading journal · dibuat otomatis', W-44, H-30);
}
let curCardEntry=null;
function showCard(id){
 const e=lastEntries.find(x=>x.id===id); if(!e) return;
 curCardEntry=e; drawShareCard(e);
 $('cardModal').style.display='flex';
}
function closeCard(){$('cardModal').style.display='none'}
function downloadCard(){
 if(!curCardEntry) return;
 const c=$('shareCanvas');
 const a=document.createElement('a'); a.download='pnl-'+(curCardEntry.sym||'trade')+'-'+curCardEntry.id+'.png';
 a.href=c.toDataURL('image/png'); a.click();
}
$('jdt').value=epochToLocalInput(Math.floor(Date.now()/1000));
function compressImg(file, maxDim, quality){
 // resize+re-encode via canvas -> jauh lebih kecil (chart-screenshot 4-8MB PNG jadi ~150-400KB JPEG),
 // efek samping BAGUS: metadata EXIF (lokasi GPS dll) otomatis kebuang krn di-re-encode dari pixel data.
 return new Promise((resolve,reject)=>{
  const img=new Image(); const url=URL.createObjectURL(file);
  img.onload=()=>{
   URL.revokeObjectURL(url);
   let w=img.naturalWidth,h=img.naturalHeight;
   if(w>maxDim||h>maxDim){const s=maxDim/Math.max(w,h);w=Math.round(w*s);h=Math.round(h*s)}
   const c=document.createElement('canvas'); c.width=w;c.height=h;
   const ctx=c.getContext('2d'); ctx.drawImage(img,0,0,w,h);
   resolve(c.toDataURL('image/jpeg',quality));
  };
  img.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('gagal baca gambar'))};
  img.src=url;
 });
}
function onPick(ev){
 const f=ev.target.files[0]; if(!f) return;
 if(f.size>15*1024*1024){$('jmsg').textContent='file >15MB, kegedean buat diproses';$('jmsg').style.color='var(--down)';ev.target.value='';return}
 removeImgFlag=false; compressing=true;
 $('jfname').textContent='⟳ mengompres…'; $('jmsg').textContent='';
 compressImg(f,1600,0.82).then(durl=>{
  compressing=false;
  const approxKB=Math.round(durl.length*0.75/1024);
  $('jfname').textContent=f.name+' (~'+approxKB+'KB setelah kompres)';
  pendingImg=durl.split(',')[1]; $('jprev').src=durl; $('jprev').style.display='block';
 }).catch(_=>{compressing=false;$('jmsg').textContent='gagal kompres gambar';$('jmsg').style.color='var(--down)';ev.target.value=''});
}
function removeImg(){pendingImg=null;removeImgFlag=true;$('jprev').style.display='none';$('jprev').src='';$('jrmimg').style.display='none';$('jfname').textContent='(gambar akan dihapus)'}
function resetForm(){
 $('jnote').value='';$('jsym').value='';$('jfile').value='';$('jfname').textContent='';$('jprev').style.display='none';$('jprev').src='';
 $('jmodal').value='';$('jentry').value='';$('jexit').value='';$('jsl').value='';$('jlev').value='';$('jpnl').value='';$('jpnlHint').textContent='';
 $('jdt').value=epochToLocalInput(Math.floor(Date.now()/1000));
 pendingImg=null;editingId=null;removeImgFlag=false; setDir(1);
 $('jformtitle').textContent='Entri Baru';$('jcancelWrap').style.display='none';$('jsavebtn').textContent='Simpan Entri';$('jrmimg').style.display='none';
}
function cancelEdit(){resetForm()}
function editEntry(id){
 const e=lastEntries.find(x=>x.id===id); if(!e) return;
 editingId=id; pendingImg=null; removeImgFlag=false;
 $('jnote').value=e.note||'';$('jsym').value=e.sym||'';$('jdt').value=epochToLocalInput(e.ts);
 $('jmodal').value=e.modal??'';$('jentry').value=e.entry??'';$('jexit').value=e.exit??'';$('jsl').value=e.sl??'';$('jlev').value=e.lev??'';$('jpnl').value=e.pnl??'';
 setDir(e.dir===-1?-1:1); $('jpnlHint').textContent='';
 $('jfile').value='';
 if(e.img){$('jprev').src='/journal_img/'+e.img;$('jprev').style.display='block';$('jfname').textContent='(gambar tersimpan — pilih file baru utk ganti)';$('jrmimg').style.display='inline-block'}
 else{$('jprev').style.display='none';$('jfname').textContent='';$('jrmimg').style.display='none'}
 $('jformtitle').textContent='Edit Entri';$('jcancelWrap').style.display='inline-block';$('jsavebtn').textContent='Update Entri';
 window.scrollTo({top:0,behavior:'smooth'});
}
function saveEntry(){
 if(compressing){$('jmsg').textContent='tunggu kompresi gambar selesai…';$('jmsg').style.color='var(--amber)';return}
 const note=$('jnote').value.trim(), sym=$('jsym').value.trim(), ts=localInputToEpoch($('jdt').value);
 const modal=$('jmodal').value, entry=$('jentry').value, exit=$('jexit').value, sl=$('jsl').value, lev=$('jlev').value, pnl=$('jpnl').value, dir=curDir;
 if(!note && !pendingImg && !(editingId && !removeImgFlag)){$('jmsg').textContent='isi catatan atau tempel screenshot dulu';$('jmsg').style.color='var(--down)';return}
 $('jmsg').textContent='⟳ menyimpan…';$('jmsg').style.color='var(--amber)';
 const payload=editingId
  ?{act:'edit',id:editingId,note,sym,ts,modal,entry,exit,sl,lev,pnl,dir,img_b64:pendingImg,remove_img:removeImgFlag}
  :{act:'add',note,sym,ts,modal,entry,exit,sl,lev,pnl,dir,img_b64:pendingImg};
 fetch('/api/journal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
  .then(r=>r.json()).then(d=>{
   $('jmsg').textContent=d.ok?'✓ tersimpan':(d.msg||'gagal');$('jmsg').style.color=d.ok?'var(--up)':'var(--down)';
   if(d.ok){resetForm();loadJournal()}
  }).catch(_=>{$('jmsg').textContent='gagal';$('jmsg').style.color='var(--down)'});
}
function delEntry(id){
 if(!confirm('Hapus entri ini?'))return;
 fetch('/api/journal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({act:'del',id})}).then(r=>r.json()).then(_=>{if(editingId===id)resetForm();loadJournal()});
}
function loadJournal(){
 fetch('/api/journal').then(r=>r.json()).then(d=>{
  lastEntries=d.entries||[];
  renderPnlCard(); renderCalendar(); renderList(); renderStats();
 }).catch(_=>{$('jlist').textContent='gagal memuat'});
}
function csvEsc(v){v=(v==null?'':String(v));return /[",\n]/.test(v)?('"'+v.replace(/"/g,'""')+'"'):v}
function exportCsv(){
 if(!lastEntries.length){alert('belum ada entri buat di-export');return}
 const cols=['tanggal','simbol','arah','modal','entry','exit','sl','leverage','pnl','catatan'];
 const rows=[cols.join(',')];
 lastEntries.slice().sort((a,b)=>a.ts-b.ts).forEach(e=>{
  rows.push([
   new Date(e.ts*1000).toISOString(), e.sym||'', e.dir===-1?'SHORT':'LONG',
   e.modal??'', e.entry??'', e.exit??'', e.sl??'', e.lev??'', e.pnl??'', e.note||''
  ].map(csvEsc).join(','));
 });
 const blob=new Blob(['﻿'+rows.join('\r\n')],{type:'text/csv;charset=utf-8'});
 const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='journal-'+new Date().toISOString().slice(0,10)+'.csv'; a.click();
 URL.revokeObjectURL(a.href);
}
function renderStats(){
 const box=$('jstats');
 if(!lastEntries.length){box.textContent='belum ada data';return}
 const withPnl=lastEntries.filter(e=>e.pnl!=null);
 if(!withPnl.length){box.textContent='isi PnL di entri dulu biar statistik kehitung';return}
 // per simbol
 const bySym={};
 withPnl.forEach(e=>{const k=e.sym||'(tanpa simbol)';const s=bySym[k]||{n:0,win:0,pnl:0};s.n++;s.pnl+=e.pnl;if(e.pnl>0)s.win++;bySym[k]=s;});
 // per hari-dalam-minggu
 const DOW=['Min','Sen','Sel','Rab','Kam','Jum','Sab']; const byDow=DOW.map(()=>({n:0,win:0,pnl:0}));
 withPnl.forEach(e=>{const dw=new Date(e.ts*1000).getDay();const s=byDow[dw];s.n++;s.pnl+=e.pnl;if(e.pnl>0)s.win++;});
 // avg win/loss + streak (urut kronologis)
 const chrono=withPnl.slice().sort((a,b)=>a.ts-b.ts);
 const wins=chrono.filter(e=>e.pnl>0), losses=chrono.filter(e=>e.pnl<0);
 const avgWin=wins.length?wins.reduce((a,e)=>a+e.pnl,0)/wins.length:0;
 const avgLoss=losses.length?losses.reduce((a,e)=>a+e.pnl,0)/losses.length:0;
 let curW=0,curL=0,maxW=0,maxL=0;
 chrono.forEach(e=>{if(e.pnl>0){curW++;curL=0;maxW=Math.max(maxW,curW);}else if(e.pnl<0){curL++;curW=0;maxL=Math.max(maxL,curL);}else{curW=0;curL=0;}});
 const best=chrono.reduce((a,e)=>e.pnl>(a?a.pnl:-Infinity)?e:a,null);
 const worst=chrono.reduce((a,e)=>e.pnl<(a?a.pnl:Infinity)?e:a,null);
 const rowsHtml=(obj,label)=>Object.entries(obj).sort((a,b)=>b[1].pnl-a[1].pnl).map(([k,s])=>
  '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--line)"><span>'+esc(k)+' <span style="color:var(--faint)">('+s.n+'t, '+Math.round(s.win/s.n*100)+'% WR)</span></span><b style="color:'+(s.pnl>=0?'var(--up)':'var(--down)')+'">'+fmtMoney(s.pnl)+'</b></div>').join('');
 box.innerHTML=
  '<div style="margin-bottom:10px"><div style="color:var(--ink);font-weight:600;margin-bottom:4px">Per simbol</div>'+rowsHtml(bySym)+'</div>'
  +'<div style="margin-bottom:10px"><div style="color:var(--ink);font-weight:600;margin-bottom:4px">Per hari</div>'+rowsHtml(Object.fromEntries(DOW.map((d,i)=>[d,byDow[i]]).filter(([,s])=>s.n>0)))+'</div>'
  +'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-top:10px">'
  +'<div><div class=label>Avg win</div><div style="color:var(--up);font-weight:600">'+fmtMoney(avgWin)+'</div></div>'
  +'<div><div class=label>Avg loss</div><div style="color:var(--down);font-weight:600">'+fmtMoney(avgLoss)+'</div></div>'
  +'<div><div class=label>Win streak terpanjang</div><div style="color:var(--ink);font-weight:600">'+maxW+'</div></div>'
  +'<div><div class=label>Loss streak terpanjang</div><div style="color:var(--ink);font-weight:600">'+maxL+'</div></div>'
  +(best?'<div><div class=label>Trade terbaik</div><div style="color:var(--up);font-weight:600">'+fmtMoney(best.pnl)+' <span style="color:var(--faint);font-weight:400">('+esc(best.sym||'-')+')</span></div></div>':'')
  +(worst?'<div><div class=label>Trade terburuk</div><div style="color:var(--down);font-weight:600">'+fmtMoney(worst.pnl)+' <span style="color:var(--faint);font-weight:400">('+esc(worst.sym||'-')+')</span></div></div>':'')
  +'</div>';
}
function renderList(){
  const fEl=$('jlistFilter');
  let es=lastEntries.slice().sort((a,b)=>b.ts-a.ts);
  if(calFilterDay){
   es=es.filter(e=>{const d=new Date(e.ts*1000);return d.getFullYear()===calFilterDay.y&&d.getMonth()===calFilterDay.m&&d.getDate()===calFilterDay.d;});
   const lbl=new Date(calFilterDay.y,calFilterDay.m,calFilterDay.d).toLocaleDateString(undefined,{weekday:'long',day:'numeric',month:'long'});
   fEl.style.display='flex';
   fEl.innerHTML='<span>📅 Nampilin <b>'+es.length+' trade</b> tanggal <b>'+lbl+'</b></span><button onclick="clearCalFilter()" style="background:none;border:1px solid var(--amber);color:var(--amber);border-radius:4px;cursor:pointer;font-size:10px;padding:3px 8px">✕ tampilkan semua</button>';
  } else {
   fEl.style.display='none'; fEl.innerHTML='';
  }
  if(!es.length){$('jlist').innerHTML='<div style="font-size:12px;color:var(--dim)">'+(calFilterDay?'nggak ada entri tanggal ini':'belum ada entri')+'</div>';return}
  $('jlist').innerHTML=es.map(e=>{
   const dtxt=new Date(e.ts*1000).toLocaleString();
   const img=e.img?('<img src="/journal_img/'+e.img+'" style="max-width:100%;max-height:260px;border-radius:6px;margin-top:8px;cursor:pointer" onclick="window.open(this.src,\'_blank\')">'):'';
   const symtag=e.sym?('<span class=tag style="margin-right:8px">'+esc(e.sym)+'</span>'):'';
   const stat=[];
   if(e.pnl!=null)stat.push('<span>PnL <b style="color:'+(e.pnl>=0?'var(--up)':'var(--down)')+'">'+(e.pnl>=0?'+':'')+'$'+Number(e.pnl).toLocaleString()+'</b></span>');
   if(e.dir!=null)stat.push('<span><b style="color:'+(e.dir===-1?'var(--down)':'var(--up)')+'">'+(e.dir===-1?'▼ SHORT':'▲ LONG')+'</b></span>');
   if(e.modal!=null)stat.push('<span>Modal <b style="color:var(--ink)">$'+Number(e.modal).toLocaleString()+'</b></span>');
   if(e.entry!=null)stat.push('<span>Entry <b style="color:var(--ink)">$'+Number(e.entry).toLocaleString()+'</b></span>');
   if(e.exit!=null)stat.push('<span>Exit <b style="color:var(--ink)">$'+Number(e.exit).toLocaleString()+'</b></span>');
   if(e.sl!=null)stat.push('<span>SL <b style="color:var(--down)">$'+Number(e.sl).toLocaleString()+'</b></span>');
   if(e.lev!=null)stat.push('<span>Lev <b style="color:var(--amber)">'+Number(e.lev)+'x</b></span>');
   const statline=stat.length?('<div style="font-size:11.5px;color:var(--dim);margin-top:7px;display:flex;gap:14px;flex-wrap:wrap">'+stat.join('')+'</div>'):'';
   return '<div style="border:1px solid var(--line);border-radius:6px;padding:11px">'
    +'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px"><span style="font-size:10.5px;color:var(--dim)">'+symtag+esc(dtxt)+'</span>'
    +'<span style="display:flex;gap:6px">'+(e.pnl!=null?('<button onclick="showCard(\''+e.id+'\')" style="background:none;border:1px solid var(--amber);color:var(--amber);border-radius:4px;cursor:pointer;font-size:10px;padding:3px 8px">🎴 pamer</button>'):'')
    +'<button onclick="editEntry(\''+e.id+'\')" style="background:none;border:1px solid var(--line);color:var(--amber2);border-radius:4px;cursor:pointer;font-size:10px;padding:3px 8px">edit</button>'
    +'<button onclick="delEntry(\''+e.id+'\')" style="background:none;border:1px solid var(--line);color:var(--down);border-radius:4px;cursor:pointer;font-size:10px;padding:3px 8px">hapus</button></span></div>'
    +statline
    +(e.note?('<div style="font-size:12.5px;margin-top:7px;white-space:pre-wrap;line-height:1.5">'+esc(e.note)+'</div>'):'')
    +img+'</div>';
  }).join('');
}
function clk(){$('ts').textContent=new Date().toUTCString().slice(5,22)+' UTC'}
loadJournal();clk();setInterval(clk,1000);
</script></body></html>"""

LOGIN=HEAD+"<title>DNAYAKA · Login</title></head><body>"+ATMOS+r"""
<div style="min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px">
 <form method=POST action="/login" style="background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:34px 30px;width:100%;max-width:340px;box-shadow:0 20px 60px rgba(0,0,0,.7)">
  <div style="font-family:var(--disp);font-weight:700;font-size:24px;color:var(--ink);text-align:center;letter-spacing:-.01em">DNAYAKA</div>
  <div style="text-align:center;font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);margin-bottom:24px">Crypto Terminal · Login</div>
  <label style="display:block;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin-bottom:5px">Username</label>
  <input name=u autocomplete=username autofocus style="width:100%;background:var(--bg);border:1px solid var(--line);border-radius:7px;color:var(--ink);font-family:var(--mono);font-size:14px;padding:12px;margin-bottom:14px;box-sizing:border-box">
  <label style="display:block;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin-bottom:5px">Password</label>
  <input name=p type=password autocomplete=current-password style="width:100%;background:var(--bg);border:1px solid var(--line);border-radius:7px;color:var(--ink);font-family:var(--mono);font-size:14px;padding:12px;margin-bottom:18px;box-sizing:border-box">
  <button type=submit style="width:100%;padding:13px;font-family:var(--mono);font-weight:600;letter-spacing:.12em;text-transform:uppercase;background:var(--amber);color:#160c00;border:0;border-radius:7px;cursor:pointer;font-size:12px">Masuk</button>
  <div id=err style="text-align:center;font-size:11px;color:var(--down);height:14px;margin-top:12px"></div>
 </form>
</div>
<script>var _s=location.search;if(_s.indexOf('e=2')>=0)document.getElementById('err').textContent='Trial habis / terlalu banyak percobaan, coba lagi nanti';else if(_s.indexOf('e=1')>=0)document.getElementById('err').textContent='Username / password salah';</script>
</body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _s(self,c,ct,b,gz=None):
        body=b if isinstance(b,(bytes,bytearray)) else b.encode()
        nocache=("html" in ct)   # HTML/JS jangan di-cache browser -> reload selalu dapat kode terbaru (cegah "masih ngebug" gara2 JS lama)
        if "gzip" in self.headers.get("Accept-Encoding","") and (gz is not None or len(body)>1024):
            if gz is None: gz=gzip.compress(body,5)
            self.send_response(c);self.send_header("Content-Type",ct);self.send_header("Access-Control-Allow-Origin","*")
            if nocache: self.send_header("Cache-Control","no-store")
            self.send_header("Content-Encoding","gzip");self.send_header("Vary","Accept-Encoding");self.send_header("Content-Length",str(len(gz)));self.end_headers()
            try: self.wfile.write(gz)
            except (BrokenPipeError,ConnectionResetError): pass
        else:
            self.send_response(c);self.send_header("Content-Type",ct);self.send_header("Access-Control-Allow-Origin","*")
            if nocache: self.send_header("Cache-Control","no-store")
            self.send_header("Content-Length",str(len(body)));self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError): pass
    def _auth_ok(self):
        if not AUTH_PASS: return False   # S2: no password set -> deny (jangan fail-open)
        h=self.headers.get("Authorization","")
        if h.startswith("Basic "):
            try:
                import hmac
                supplied=base64.b64decode(h[6:]).decode("utf-8","ignore").split(":",1)[-1]
                return hmac.compare_digest(supplied, AUTH_PASS)   # S8: constant-time
            except Exception: return False
        return False
    def _need_auth(self):
        self.send_response(401);self.send_header("WWW-Authenticate",'Basic realm="IDX Terminal"');self.send_header("Content-Type","text/plain");self.end_headers();self.wfile.write(b"auth required")
    def _cookie_tok(self):
        for part in self.headers.get("Cookie","").split(";"):
            part=part.strip()
            if part.startswith("sid="): return part[4:]
        return None
    def _user(self): return session_user(self._cookie_tok())
    def _is_local(self):   # akses langsung dari laptop ini (BUKAN lewat tunnel cloudflared) -> tanpa login
        return self.client_address[0] in ("127.0.0.1","::1","localhost") and not self.headers.get("CF-Connecting-IP") and not self.headers.get("X-Forwarded-For")
    def _client_ip(self):  # IP asli (di balik tunnel ada di header CF/XFF), buat rate-limit
        return (self.headers.get("CF-Connecting-IP") or self.headers.get("X-Forwarded-For","").split(",")[0].strip() or self.client_address[0])
    def _redirect(self,loc,cookie=None):
        self.send_response(302);self.send_header("Location",loc)
        if cookie: self.send_header("Set-Cookie",cookie)
        self.send_header("Content-Length","0");self.end_headers()
        try: self.wfile.write(b"")
        except Exception: pass
    def do_POST(self):
        path=urlparse(self.path).path
        ip=self._client_ip(); local=self._is_local()
        if not local and not _rl_ok(ip): return self._s(429,"application/json",'{"error":"rate limit"}')   # anti-DDoS
        if path=="/login":   # form login -> verify -> set session cookie
            if _login_blocked(ip): return self._redirect("/login?e=2")   # anti brute-force (8 gagal/5mnt)
            try:
                n=max(0,min(int(self.headers.get("Content-Length",0)),4096)); raw=self.rfile.read(n).decode("utf-8","ignore") if n else ""
                f=parse_qs(raw); user=(f.get("u",[""])[0] or "").strip(); pw=f.get("p",[""])[0] or ""
            except Exception: return self._redirect("/login?e=1")
            if verify_user(user,pw):
                return self._redirect("/", "sid="+make_session(user)+"; HttpOnly; Path=/; SameSite=Lax; Max-Age="+str(SESS_TTL))
            _login_fail(ip)
            return self._redirect("/login?e=1")
        usr=self._user()
        jusr = usr or (local and "local")
        if path=="/api/journal":   # per-user, BUKAN admin-only -- siapapun yg login boleh tulis journal-nya sendiri
            if not jusr: return self._s(401,"application/json",'{"ok":false,"msg":"login required"}')
            try:
                cap=int(JCAP_IMG_BYTES*1.4)+8192
                n=max(0,min(int(self.headers.get("Content-Length",0)),cap)); body=json.loads(self.rfile.read(n)) if n else {}
            except Exception: return self._s(400,"application/json",'{"ok":false,"msg":"bad body"}')
            act=body.get("act","add")
            def _mkts():   # ts dari client (datetime-local, epoch detik) -- fallback now kalau kosong/rusak
                try:
                    v=int(body.get("ts") or 0)
                    return v if 0<v<4102444800 else int(_time.time())   # sanity: >0 dan <thn2100
                except Exception: return int(_time.time())
            def _num(key):   # -> float atau None (SL/leverage/dll opsional, jangan paksa 0)
                v=body.get(key)
                if v in (None,""): return None
                try:
                    f=float(v)
                    return f if abs(f)<1e12 else None   # sanity cap, tolak angka absurd
                except Exception: return None
            def _saveimg(b64):   # -> (img_id, err_response) -- err_response None kalau sukses
                try: raw=base64.b64decode(b64, validate=True)
                except Exception: return None,self._s(400,"application/json",'{"ok":false,"msg":"gambar tak valid"}')
                if len(raw)>JCAP_IMG_BYTES: return None,self._s(400,"application/json",'{"ok":false,"msg":"gambar >2MB"}')
                ext=_detect_img(raw)
                if not ext: return None,self._s(400,"application/json",'{"ok":false,"msg":"format gambar tak didukung (jpg/png/webp)"}')
                os.makedirs(JIMG_DIR,exist_ok=True)
                img_id=_secrets.token_hex(16)+"."+ext
                with open(os.path.join(JIMG_DIR,img_id),"wb") as f: f.write(raw)
                return img_id,None
            with _JLK:
                d=_jload(); mine=d.setdefault(jusr,[])
                if act=="del":
                    iid=body.get("id","")
                    removed=[e for e in mine if e.get("id")==iid]
                    d[jusr]=[e for e in mine if e.get("id")!=iid]; _jsave(d)
                    for e in removed:
                        if e.get("img"):
                            try: os.remove(os.path.join(JIMG_DIR,e["img"]))
                            except Exception: pass
                    return self._s(200,"application/json",'{"ok":true}')
                if act=="edit":
                    iid=body.get("id",""); tgt=next((e for e in mine if e.get("id")==iid),None)
                    if not tgt: return self._s(404,"application/json",'{"ok":false,"msg":"entri tak ditemukan"}')
                    tgt["note"]=str(body.get("note") or "")[:2000]; tgt["sym"]=str(body.get("sym") or "")[:20]
                    tgt["ts"]=_mkts()
                    tgt["modal"]=_num("modal"); tgt["entry"]=_num("entry"); tgt["sl"]=_num("sl"); tgt["lev"]=_num("lev"); tgt["pnl"]=_num("pnl"); tgt["exit"]=_num("exit"); tgt["dir"]=(-1 if body.get("dir")==-1 or body.get("dir")=="-1" else 1)
                    if body.get("remove_img"):
                        if tgt.get("img"):
                            try: os.remove(os.path.join(JIMG_DIR,tgt["img"]))
                            except Exception: pass
                        tgt["img"]=None
                    elif body.get("img_b64"):
                        img_id,err=_saveimg(body["img_b64"])
                        if err: return err
                        old=tgt.get("img")
                        tgt["img"]=img_id
                        if old:
                            try: os.remove(os.path.join(JIMG_DIR,old))
                            except Exception: pass
                    d[jusr]=mine; _jsave(d)
                    return self._s(200,"application/json",json.dumps({"ok":True,"entry":tgt}))
                # act == add
                if len(mine)>=JCAP_ENTRIES:
                    return self._s(200,"application/json",json.dumps({"ok":False,"msg":f"limit {JCAP_ENTRIES} entri tercapai, hapus yg lama dulu"}))
                note=str(body.get("note") or "")[:2000]; sym=str(body.get("sym") or "")[:20]
                img_id=None; b64=body.get("img_b64")
                if b64:
                    img_id,err=_saveimg(b64)
                    if err: return err
                entry={"id":_secrets.token_hex(8),"ts":_mkts(),"note":note,"sym":sym,"img":img_id,
                       "modal":_num("modal"),"entry":_num("entry"),"sl":_num("sl"),"lev":_num("lev"),"pnl":_num("pnl"),
                       "exit":_num("exit"),"dir":(-1 if body.get("dir")==-1 or body.get("dir")=="-1" else 1)}
                mine.append(entry); d[jusr]=mine; _jsave(d)
            return self._s(200,"application/json",json.dumps({"ok":True,"entry":entry}))
        if path=="/api/alerts":   # per-user, web-only (nol WA/push) -- FE polling ngecek selama tab kebuka
            if not jusr: return self._s(401,"application/json",'{"ok":false,"msg":"login required"}')
            try:
                n=max(0,min(int(self.headers.get("Content-Length",0)),4096)); body=json.loads(self.rfile.read(n)) if n else {}
            except Exception: return self._s(400,"application/json",'{"ok":false,"msg":"bad body"}')
            act=body.get("act","add")
            with _ALK:
                d=_aload(); mine=d.setdefault(jusr,[])
                if act=="del":
                    iid=body.get("id",""); d[jusr]=[a for a in mine if a.get("id")!=iid]; _asave(d)
                    return self._s(200,"application/json",'{"ok":true}')
                if act=="ack":   # tandai udah trigger -> nonaktif (one-shot, jangan spam berulang)
                    iid=body.get("id","")
                    for a in mine:
                        if a.get("id")==iid: a["active"]=False; a["triggered_at"]=int(_time.time())
                    d[jusr]=mine; _asave(d)
                    return self._s(200,"application/json",'{"ok":true}')
                # act == add
                if len(mine)>=ALERTS_CAP:
                    return self._s(200,"application/json",json.dumps({"ok":False,"msg":f"limit {ALERTS_CAP} alert tercapai, hapus yg lama dulu"}))
                sym=str(body.get("sym") or "BTCUSDT")[:12]
                if sym not in ("BTCUSDT","ETHUSDT","SOLUSDT"): return self._s(400,"application/json",'{"ok":false,"msg":"simbol tak dikenal"}')
                typ="rsi" if body.get("type")=="rsi" else "price"
                op="<=" if body.get("op")=="<=" else ">="
                try: value=float(body.get("value"))
                except Exception: return self._s(400,"application/json",'{"ok":false,"msg":"nilai tak valid"}')
                if typ=="rsi": value=max(0,min(100,value))
                alert={"id":_secrets.token_hex(8),"sym":sym,"type":typ,"op":op,"value":value,
                       "active":True,"created":int(_time.time()),"triggered_at":None}
                mine.append(alert); d[jusr]=mine; _asave(d)
            return self._s(200,"application/json",json.dumps({"ok":True,"alert":alert}))
        if not (local or (usr and is_admin(usr)) or self._auth_ok()): return self._need_auth()   # POST admin = localhost ATAU session-admin ATAU service basic-auth
        if path=="/api/users":   # admin: kelola user (signup HANYA di sini)
            try:
                n=max(0,min(int(self.headers.get("Content-Length",0)),8192)); body=json.loads(self.rfile.read(n)) if n else {}
            except Exception: return self._s(400,"application/json",'{"ok":false}')
            act=body.get("act"); un=(body.get("user") or "").strip()
            if act=="list": return self._s(200,"application/json",json.dumps({"users":list_users()}))
            if act=="add" and un and body.get("pw"): add_user(un,body["pw"],bool(body.get("admin")),int(body.get("days",0) or 0)); return self._s(200,"application/json",'{"ok":true}')
            if act=="expiry" and un: set_expiry(un,int(body.get("days",0) or 0)); return self._s(200,"application/json",'{"ok":true}')
            if act=="del" and un and un!=usr: del_user(un); return self._s(200,"application/json",'{"ok":true}')
            return self._s(400,"application/json",'{"ok":false,"msg":"bad / tak bisa hapus diri sendiri"}')
        if self.path=="/api/refresh_stocks":
            err=None
            with _JOBLK:                                   # S4: single-flight (cegah spawn bertumpuk -> CPU/file korup)
                pj=_JOBS.get("stocks"); busy=bool(pj and pj.poll() is None)
                if not busy:
                    try: _JOBS["stocks"]=subprocess.Popen(["bash","-c","python3 idx_data.py && python3 signal_stocks.py --update --ai"], cwd=STOCKS_DIR, stdout=open(STOCKS_DIR+"/signal.log","a"), stderr=subprocess.STDOUT)
                    except Exception as e: err=str(e)[:120]
            if busy: return self._s(200,"application/json",'{"ok":false,"msg":"refresh masih jalan, tunggu."}')
            if err:  return self._s(200,"application/json",json.dumps({"ok":False,"msg":err}))
            return self._s(200,"application/json",'{"ok":true,"msg":"Refresh jalan (idx foreign-flow + fetch + sinyal + AI bandar, ~5-10 mnt). Proton OFF biar IDX kebuka. Refresh /saham nanti."}')
        if self.path=="/api/idx_cookie":
            try:                                           # S7: body di dalam try + cap 64KB
                n=max(0,min(int(self.headers.get("Content-Length",0)),65536)); body=json.loads(self.rfile.read(n)) if n else {}
            except Exception: return self._s(400,"application/json",'{"ok":false,"msg":"bad body"}')
            try:
                json.dump({"cookie":body.get("cookie",""),"ua":body.get("ua","")}, open(STOCKS_DIR+"/.idx_cookie","w"))
                os.chmod(STOCKS_DIR+"/.idx_cookie",0o600)
            except Exception as e: return self._s(200,"application/json",json.dumps({"ok":False,"msg":str(e)[:120]}))
            err=None
            with _JOBLK:
                pj=_JOBS.get("broksum"); busy=bool(pj and pj.poll() is None)
                if not busy:
                    try: _JOBS["broksum"]=subprocess.Popen(["python3","idx_broksum.py"], cwd=STOCKS_DIR, stdout=open(STOCKS_DIR+"/broksum.log","a"), stderr=subprocess.STDOUT)
                    except Exception as e: err=str(e)[:120]
            if busy: return self._s(200,"application/json",'{"ok":false,"msg":"broksum masih jalan, tunggu."}')
            if err:  return self._s(200,"application/json",json.dumps({"ok":False,"msg":err}))
            return self._s(200,"application/json",'{"ok":true,"msg":"Cookie tersimpan. Fetch broksum jalan (~30 dtk). Refresh /saham."}')
        return self._s(404,"application/json",'{"ok":false}')
    def do_GET(self):
        p=urlparse(self.path); path=p.path
        if path=="/favicon.ico":   # browser lama yg ga baca <link rel=icon> minta path ini default -> kasih icon beneran (bukan 204 kosong)
            return self._s(200,"image/svg+xml",FAVICON_SVG)
        if path=="/manifest.json": return self._s(200,"application/manifest+json",PWA_MANIFEST)
        if path=="/sw.js": return self._s(200,"application/javascript",SW_JS)
        if path=="/icons/icon-192.png": return self._s(200,"image/png",ICON_192) if ICON_192 else self._s(404,"text/plain","not found")
        if path=="/icons/icon-512.png": return self._s(200,"image/png",ICON_512) if ICON_512 else self._s(404,"text/plain","not found")
        local=self._is_local()
        if not local and not _rl_ok(self._client_ip()): return self._s(429,"application/json",'{"error":"rate limit"}')   # anti-DDoS
        if path=="/login":
            if local: return self._redirect("/")          # localhost ga perlu login
            return self._s(200,"text/html",LOGIN)
        if path=="/logout": del_session(self._cookie_tok()); return self._redirect("/login","sid=; HttpOnly; Path=/; Max-Age=0")
        usr=self._user()
        if path=="/admin":                              # admin-role only (localhost = admin)
            if not (local or (usr and is_admin(usr))): return self._redirect("/login")
            return self._s(200,"text/html",ADMINP)
        if path=="/":          # page butuh login (kecuali localhost) -- /performa & /saham PINDAH ke admin :8789
            if not (local or usr): return self._redirect("/login")
            return self._s(200,"text/html", MAIN)
        jusr = usr or (local and "local")   # journal butuh IDENTITAS nyata (per-user) -- localhost dapat pseudo-user "local", BUKAN bypass total kayak halaman lain
        if path=="/journal":
            if not jusr: return self._redirect("/login")
            return self._s(200,"text/html", JOURNAL)
        if path=="/api/journal":
            if not jusr: return self._s(401,"application/json",'{"error":"login required"}')
            return self._s(200,"application/json", json.dumps({"entries":_jload().get(jusr,[])}))
        if path=="/api/alerts":
            if not jusr: return self._s(401,"application/json",'{"error":"login required"}')
            return self._s(200,"application/json", json.dumps({"alerts":_aload().get(jusr,[])}))
        if path.startswith("/journal_img/"):
            if not jusr: return self._s(401,"text/plain","login required")
            import re as _re
            iid=path[len("/journal_img/"):]
            if not _re.fullmatch(r"[a-f0-9]{32}\.(jpg|png|webp)", iid): return self._s(400,"text/plain","bad id")
            mine=_jload().get(jusr,[])
            if not any(e.get("img")==iid for e in mine): return self._s(404,"text/plain","not found")   # ownership check -- id server-random tapi tetap wajib punya sendiri
            fp=os.path.join(JIMG_DIR,iid)
            if not os.path.isfile(fp) or os.path.getsize(fp)>JCAP_IMG_BYTES: return self._s(404,"text/plain","not found")
            with open(fp,"rb") as f: raw=f.read()
            ext2=_detect_img(raw)   # re-verify magic-bytes SAAT SERVE juga (bukan cuma upload) -- kalau file di disk somehow beda dari ekstensi namanya, refuse drpd percaya buta
            if not ext2 or iid.rsplit(".",1)[-1]!=ext2: return self._s(415,"text/plain","corrupt/mismatched file, refused")
            ct={"jpg":"image/jpeg","png":"image/png","webp":"image/webp"}[ext2]
            self.send_response(200); self.send_header("Content-Type",ct); self.send_header("Content-Length",str(len(raw)))
            self.send_header("X-Content-Type-Options","nosniff"); self.send_header("Content-Disposition","inline")
            self.send_header("Cache-Control","private, max-age=3600"); self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError): pass
            return
        if path.startswith("/api/") and not (local or usr or self._auth_ok()):   # API anti-scrape: localhost ATAU login (cookie) ATAU service basic-auth (ai_gen)
            return self._s(401,"application/json",'{"error":"login required"}')
        if path=="/api/btc_v20":
            raw,gz=v20_blob()
            return self._s(200,"application/json",raw,gz=gz)
        if path in ("/api/eth_v20","/api/sol_v20"):   # strategi v20 per-ticker (param vol-normalized, gen_v20.py cron)
            sym="ETHUSDT" if path=="/api/eth_v20" else "SOLUSDT"
            raw,gz=multi_v20_blob(sym)
            return self._s(200,"application/json",raw,gz=gz)
        if path=="/api/compare":   # ringkasan BTC/ETH/SOL berdampingan (harga/funding/v20 backtest) -- panel perbandingan
            def _prod():
                out={}
                vpath={"BTCUSDT":_V20PATH,"ETHUSDT":_MV20PATH["ETHUSDT"],"SOLUSDT":_MV20PATH["SOLUSDT"]}
                for sym in ("BTCUSDT","ETHUSDT","SOLUSDT"):
                    d={}
                    try:
                        j=bget("/fapi/v1/premiumIndex?symbol="+sym) or {}
                        d["mark"]=float(j.get("markPrice",0)); d["funding"]=float(j.get("lastFundingRate",0))*100
                    except Exception: pass
                    try:
                        tk=bget("/fapi/v1/ticker/24hr?symbol="+sym) or {}
                        d["chg24h"]=float(tk.get("priceChangePercent",0))
                    except Exception: pass
                    try:
                        vj=json.load(open(vpath[sym])); perf=vj.get("perf",{})
                        d["v20_ret"]=perf.get("ret"); d["v20_wr"]=perf.get("wr"); d["v20_cal"]=perf.get("cal"); d["v20_n"]=perf.get("n")
                    except Exception: pass
                    out[sym]=d
                try:   # cuma BTC yg punya eksekusi bot live (v20-only sleeve)
                    st=json.load(open(os.path.join(_JHERE,"bot_v22_state.json"))); v=st.get("v20",{}); pos=int(v.get("pos",0))
                    out["BTCUSDT"]["live_dir"]=pos; out["BTCUSDT"]["live_state"]="LONG" if pos>0 else ("SHORT" if pos<0 else "WAIT")
                except Exception: pass
                return json.dumps(out)
            return self._s(200,"application/json",cache_get(("compare",),10,_prod))
        if path=="/api/signal":   # sinyal v20 SEKARANG (sanitized dari bot_v22_state: arah+entry+tp+sl, TANPA equity/key). Buat banner publik.
            def _prod():
                o={"dir":0,"state":"WAIT"}
                try:
                    st=json.load(open("/home/dnayaka/Documents/dynamic_rsi/btc-terminal/bot_v22_state.json"))
                    v=st.get("v20",{}); pos=int(v.get("pos",0))
                    o["dir"]=pos
                    o["state"]="LONG" if pos>0 else ("SHORT" if pos<0 else "WAIT")
                    if pos!=0:
                        o["entry"]=round(float(v.get("entry",0)),1); o["tp"]=round(float(v.get("tp",0)),1); o["sl"]=round(float(v.get("sl",0)),1)
                    o["last"]=st.get("last_open_time",0)
                    br=st.get("breaker",{})
                    if br.get("halted"): o["halted"]=True; o["reason"]=br.get("reason","")
                except Exception: pass
                try: o["price"]=float((bget("/fapi/v1/ticker/price?symbol=BTCUSDT") or {}).get("price",0))
                except: pass
                return json.dumps(o)
            return self._s(200,"application/json",cache_get(("signal",),10,_prod))
        if path=="/api/dxy":   # US Dollar Index (Yahoo DX-Y.NYB) — lihat BTC melemah/menguat vs dollar (korelasi terbalik)
            def _prod():
                yurl="https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?range=6mo&interval=1d"
                for u in (yurl, "https://proxy.cors.sh/"+yurl):   # direct (Proton) -> proxy fallback
                    try:
                        r=S.get(u,timeout=12,verify=False,headers={"User-Agent":"Mozilla/5.0"})
                        res=r.json()["chart"]["result"][0]; ts=res["timestamp"]; cl=res["indicators"]["quote"][0]["close"]
                        ser=[[int(t),round(float(c),3)] for t,c in zip(ts,cl) if c is not None]
                        if len(ser)<2: continue
                        last=ser[-1][1]; prev=ser[-2][1]; d30=ser[-22][1] if len(ser)>=22 else ser[0][1]
                        return json.dumps({"series":ser,"last":last,"chg":round((last/prev-1)*100,2),"chg30":round((last/d30-1)*100,2)})
                    except Exception: continue
                return json.dumps({"series":[]})
            return self._s(200,"application/json",cache_get(("dxy",),1800,_prod))
        if path=="/api/klines":
            sym=sym_of(p); tf=parse_qs(p.query).get("tf",["15m"])[0]
            if tf not in _TFOK: tf="15m"   # whitelist -> cegah unbounded cache key
            def _prod():
                kl=bget(f"/fapi/v1/klines?symbol={sym}&interval={tf}&limit=500")
                if not kl: return "[]"
                try:
                    return json.dumps([{"time":int(k[0]//1000),"open":float(k[1]),"high":float(k[2]),"low":float(k[3]),"close":float(k[4]),"volume":float(k[5])} for k in kl])
                except: return "[]"
            return self._s(200,"application/json",cache_get(("klines",sym,tf),3,_prod))
        if path=="/api/metrics":
            sym=sym_of(p)
            def _fng():
                try:
                    f=S.get("https://api.alternative.me/fng/?limit=1",timeout=8,verify=False).json()["data"][0]
                    return [str(f["value"]), f["value_classification"].replace("Extreme ","E.")]
                except: return ["-",""]
            def _prod():
                d={"funding":0,"mark":0,"fng":"-","fng_txt":""}
                try:
                    j=bget("/fapi/v1/premiumIndex?symbol="+sym) or {}
                    d["funding"]=float(j["lastFundingRate"])*100; d["mark"]=float(j["markPrice"])
                except: pass
                try:
                    fv=cache_get(("fng",),300,_fng); d["fng"]=fv[0]; d["fng_txt"]=fv[1]
                except: pass
                return json.dumps(d)
            return self._s(200,"application/json",cache_get(("metrics",sym),3,_prod))
        if path=="/api/global":
            def _prod():
                try:
                    j=S.get("https://api.coingecko.com/api/v3/global",timeout=10,verify=False).json()["data"]
                    _G["d"]={"dom":j["market_cap_percentage"]["btc"],"mcap":j["total_market_cap"]["usd"]/1e12,"mcapch":j["market_cap_change_percentage_24h_usd"]}
                except: pass
                return json.dumps(_G["d"])
            return self._s(200,"application/json",cache_get(("global",),120,_prod))
        if path=="/api/fx":   # kurs USD->IDR (cache 1 jam)
            def _prod():
                try:
                    j=S.get("https://open.er-api.com/v6/latest/USD",timeout=8,verify=False).json()
                    r=float(j["rates"]["IDR"]); _FXLAST[0]=r; return json.dumps({"idr":r})
                except: return json.dumps({"idr":_FXLAST[0]})   # H5: pakai last-good, bukan 16000 mati
            return self._s(200,"application/json",cache_get(("fx",),3600,_prod))
        if path=="/api/ai":
            return self._s(200,"application/json",file_get("/home/dnayaka/Documents/dynamic_rsi/btc-terminal/ai_read.json",'{"off":true}'))
        if path=="/api/fed":   # rangkuman AI event The Fed (hawkish/dovish + ID) dari fed_summary.py, server cuma baca file
            return self._s(200,"application/json",file_get("/home/dnayaka/Documents/dynamic_rsi/btc-terminal/fed_summary.json",'{"active":false}'))
        if path=="/api/fedlive":   # video Fed Live (MANUAL, admin yg isi via :8789) -- server publik cuma baca file, NOL key
            return self._s(200,"application/json",file_get("/home/dnayaka/Documents/dynamic_rsi/btc-terminal/fed_live.json",'{"video_id":""}'))
        if path=="/api/ihsg_ta":
            try:
                with open("/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks/ihsg_ta.json") as f: d=f.read()
            except Exception: d='{}'
            return self._s(200,"application/json",d)
        if path=="/api/stock_signal":
            try:
                with open("/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks/stocks_signal.json") as f: d=f.read()
            except Exception: d='{}'
            return self._s(200,"application/json",d)
        if path=="/api/broksum":
            try:
                with open(STOCKS_DIR+"/broksum.json") as f: d=f.read()
            except Exception: d='{"_ok":false}'
            return self._s(200,"application/json",d)
        if path=="/api/stock_klines":
            import csv as _csv, re as _re2   # os JANGAN di-re-import lokal -- bikin shadow ke seluruh do_GET (UnboundLocalError di branch lain yg pakai os module-level)
            sym=parse_qs(p.query).get("sym",["^JKSE"])[0]
            if not _re2.fullmatch(r"[A-Za-z0-9.^]{1,12}", sym):   # whitelist -> cegah path traversal (sym mentah dari publik)
                return self._s(200,"application/json","[]")
            base="/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks"; rbase=os.path.realpath(base)
            fn=sym.replace("^","_")+".csv"; out=[]
            for fp in (base+"/data/"+fn, base+"/data_lowcap/"+fn):
                rp=os.path.realpath(fp)
                if not (rp.startswith(rbase+os.sep) and os.path.exists(rp)): continue   # escape dir -> tolak
                try:
                    with open(rp) as f:
                        for row in _csv.DictReader(f):
                            out.append({"time":row["dt"][:10],"open":float(row["open"]),"high":float(row["high"]),"low":float(row["low"]),"close":float(row["close"]),"volume":float(row.get("volume") or 0)})
                except Exception: pass
                break
            return self._s(200,"application/json",json.dumps(out[-500:]))
        if path=="/api/stats":
            sym=sym_of(p)
            def _prod():
                try:
                    j=bget("/fapi/v1/ticker/24hr?symbol="+sym) or {}
                    d={"high":float(j["highPrice"]),"low":float(j["lowPrice"]),"quoteVol":float(j["quoteVolume"]),"change":float(j["priceChangePercent"]),"wavg":float(j["weightedAvgPrice"]),"trades":int(j["count"])}
                    _STATSLAST[sym]=d   # stale-on-error: simpan hasil BAGUS terakhir per-sym
                except Exception:
                    d=_STATSLAST.get(sym) or {"high":0,"low":0,"quoteVol":0,"change":0,"wavg":0,"trades":0}   # fallback data lama, JANGAN cache nol ke semua pengunjung
                return json.dumps(d)
            return self._s(200,"application/json",cache_get(("stats",sym),20,_prod))
        if path=="/api/liquidity":
            sym=sym_of(p)
            def _prod():
                d={}
                try:
                    ob=bget(f"/fapi/v1/depth?symbol={sym}&limit=100") or {}
                    mid=(float(ob["bids"][0][0])+float(ob["asks"][0][0]))/2
                    bl=sum(float(pp)*float(q) for pp,q in ob["bids"] if float(pp)>=mid*0.98)
                    al=sum(float(pp)*float(q) for pp,q in ob["asks"] if float(pp)<=mid*1.02)
                    if bl+al>0: d["imb"]=bl/(bl+al)*100
                    bw=max(ob["bids"],key=lambda x:float(x[1])); aw=max(ob["asks"],key=lambda x:float(x[1]))
                    d["bidWall"]=[float(bw[0]),float(bw[1])]; d["askWall"]=[float(aw[0]),float(aw[1])]
                except: pass
                try: d["oi"]=float((bget("/fapi/v1/openInterest?symbol="+sym) or {})["openInterest"])
                except: pass
                try:   # RETAIL (akun ritel) — persen long/short + nilai SEBELUMNYA (limit=2, urut ascending -> [-1]=kini [-2]=sebelum)
                    a=bget(f"/futures/data/globalLongShortAccountRatio?symbol={sym}&period=5m&limit=2") or []
                    r=a[-1]; d["ls"]=float(r["longShortRatio"]); d["ls_l"]=round(float(r["longAccount"])*100,1); d["ls_s"]=round(float(r["shortAccount"])*100,1)
                    d["ls_ts"]=int(r["timestamp"])//1000   # sumber Binance publish tiap 5mnt -- angka MEMANG statis diantaranya, bukan bug; ts ini dipakai FE tampilin "update Xm lalu"
                    if len(a)>=2: d["ls_l0"]=round(float(a[-2]["longAccount"])*100,1)
                except: pass
                try:   # WHALE (top trader posisi) — persen long/short + sebelumnya
                    a=bget(f"/futures/data/topLongShortPositionRatio?symbol={sym}&period=5m&limit=2") or []
                    r=a[-1]; d["top"]=float(r["longShortRatio"]); d["top_l"]=round(float(r["longAccount"])*100,1); d["top_s"]=round(float(r["shortAccount"])*100,1)
                    d["top_ts"]=int(r["timestamp"])//1000
                    if len(a)>=2: d["top_l0"]=round(float(a[-2]["longAccount"])*100,1)
                except: pass
                try:   # TAKER buy/sell — persen dari volume aktual + sebelumnya
                    a=bget(f"/futures/data/takerlongshortRatio?symbol={sym}&period=5m&limit=2") or []
                    r=a[-1]; d["taker"]=float(r["buySellRatio"]); bv=float(r["buyVol"]); sv=float(r["sellVol"]); tot=bv+sv
                    if tot>0: d["tk_b"]=round(bv/tot*100,1); d["tk_s"]=round(sv/tot*100,1)
                    d["tk_ts"]=int(r["timestamp"])//1000
                    if len(a)>=2:
                        b2=float(a[-2]["buyVol"]); s2=float(a[-2]["sellVol"]); t2=b2+s2
                        if t2>0: d["tk_b0"]=round(b2/t2*100,1)
                except: pass
                return json.dumps(d)
            return self._s(200,"application/json",cache_get(("liquidity",sym),8,_prod))
        if path=="/api/liqmap":   # STANDAR/AWAL: synthetic liq heatmap (proyeksi level liq leverage-tier dari klaster harga, ESTIMASI bukan data exchange). Versi Coinalyze/real = liq_real.json (tak dipakai LIQ; user minta balik standar).
            sym=sym_of(p)
            def _prod():
                try:
                    kl=bget(f"/fapi/v1/klines?symbol={sym}&interval=1h&limit=500") or []
                    px=float(kl[-1][4]); tiers=[(10,0.15),(25,0.30),(50,0.30),(100,0.25)]; mm=0.005
                    from collections import defaultdict
                    binw=px*0.0025   # bin 0.25%
                    # tiap bin liq = agregat BANYAK kombinasi (entry-candle, leverage) yg kebetulan proyeksi ke harga sama.
                    # Simpan kombinasi PALING BESAR kontribusinya per bin -> "asumsi entry+leverage" yg ditampilkan pas diklik.
                    mk=lambda:{"v":0.0,"top":0.0,"entry":0.0,"lev":0}
                    longb=defaultdict(mk); shortb=defaultdict(mk)
                    for k in kl:
                        e=(float(k[2])+float(k[3]))/2; vol=float(k[7])   # k[7]=quoteAssetVolume (proxy ukuran posisi)
                        for lev,w in tiers:
                            contrib=vol*w
                            bl=round(e*(1-1.0/lev+mm)/binw); dl=longb[bl]; dl["v"]+=contrib
                            if contrib>dl["top"]: dl["top"]=contrib; dl["entry"]=e; dl["lev"]=lev
                            bs=round(e*(1+1.0/lev-mm)/binw); ds=shortb[bs]; ds["v"]+=contrib
                            if contrib>ds["top"]: ds["top"]=contrib; ds["entry"]=e; ds["lev"]=lev
                    bins=([{"price":round(b*binw,1),"side":"long","v":d["v"],"entry":round(d["entry"],1),"lev":d["lev"]} for b,d in longb.items()]
                        + [{"price":round(b*binw,1),"side":"short","v":d["v"],"entry":round(d["entry"],1),"lev":d["lev"]} for b,d in shortb.items()])
                    bins=[x for x in bins if (x["side"]=="long" and x["price"]<px) or (x["side"]=="short" and x["price"]>px)]   # cuma liq belum ke-trigger: long-liq di BAWAH harga, short-liq di ATAS
                    mx_raw=max((x["v"] for x in bins),default=1) or 1
                    mx=_liqmax_smooth(sym, mx_raw)   # FIX flicker: EMA-smooth lintas-fetch, jangan cuma max batch-ini
                    for x in bins:
                        x["v"]=round(min(1.0, x["v"]/mx),4)   # cap 1.0 -- batch bisa sesaat lebih terang dari smoothed-max
                        x["str"]="kuat" if x["v"]>=0.6 else ("sedang" if x["v"]>=0.25 else "lemah")
                    bins=sorted([x for x in bins if x["v"]>=0.04],key=lambda x:-x["v"])[:120]
                    return json.dumps({"mid":px,"binw":round(binw,1),"bins":bins})
                except Exception:
                    return json.dumps({"bins":[]})
            return self._s(200,"application/json",cache_get(("liqmap",sym),60,_prod))
        if path=="/api/liqreal":   # LIKUIDASI NYATA (Coinalyze 30hr) dari liq_real.json — toggle LIQ* (experimental). Server BACA file, NOL key.
            sym=sym_of(p)
            def _prod():
                try:
                    with open("/home/dnayaka/Documents/dynamic_rsi/btc-terminal/liq_real.json") as f:
                        v=json.load(f).get(sym)
                    if not v: return json.dumps({"bins":[]})
                    return json.dumps({"mid":v["mid"],"binw":v["binw"],"bins":v["bins"],"long_total":v.get("long_total"),"short_total":v.get("short_total")})
                except Exception:
                    return json.dumps({"bins":[]})
            return self._s(200,"application/json",cache_get(("liqreal",sym),60,_prod))
        if path=="/api/obmap":   # profil ORDER BOOK NYATA (resting liquidity per harga, akumulasi waktu) dari ob_record.py -> ob_liq.json. Server publik NOL key, cuma BACA file.
            sym=sym_of(p)
            def _prod():
                try:
                    with open("/home/dnayaka/Documents/dynamic_rsi/btc-terminal/ob_liq.json") as f:
                        v=json.load(f).get(sym)
                    if not v: return json.dumps({"bins":[]})
                    return json.dumps({"mid":v["mid"],"binw":v["binw"],"bins":v["bins"],"bid_total":v.get("bid_total"),"ask_total":v.get("ask_total"),"samples":v.get("samples"),"updated":v.get("updated")})
                except Exception:
                    return json.dumps({"bins":[]})
            return self._s(200,"application/json",cache_get(("obmap",sym),20,_prod))
        if path=="/api/walls":   # tembok orderbook ASLI (limit gede) = S/R nyata. ijo=bid(support), merah=ask(resist)
            sym=sym_of(p)
            def _prod():
                try:
                    ob=bget(f"/fapi/v1/depth?symbol={sym}&limit=1000") or {}
                    bids=[(float(pp),float(q)) for pp,q in ob["bids"]]; asks=[(float(pp),float(q)) for pp,q in ob["asks"]]
                    mid=(bids[0][0]+asks[0][0])/2
                    from collections import defaultdict
                    step=100.0 if mid>=10000 else (10.0 if mid>=1000 else (1.0 if mid>=100 else 0.1))   # bin round $100 (BTC), align angka bulat
                    bb=defaultdict(float); ab=defaultdict(float)
                    for pp,q in bids: bb[round(pp/step)]+=q
                    for pp,q in asks: ab[round(pp/step)]+=q
                    bwall=sorted(bb.items(),key=lambda x:-x[1])[:5]; awall=sorted(ab.items(),key=lambda x:-x[1])[:5]
                    mx=max([v for _,v in bwall+awall],default=1) or 1
                    walls=[{"price":round(b*step,1),"qty":round(v,1),"side":"bid","v":round(v/mx,3)} for b,v in bwall]+\
                          [{"price":round(b*step,1),"qty":round(v,1),"side":"ask","v":round(v/mx,3)} for b,v in awall]
                    return json.dumps({"mid":round(mid,1),"walls":walls})
                except Exception: return json.dumps({"walls":[]})
            return self._s(200,"application/json",cache_get(("walls",sym),6,_prod))
        if path=="/api/snr":   # support/resistance AUTO dari pivot price-action (swing high/low, cluster, touch>=2)
            sym=sym_of(p); tf=parse_qs(p.query).get("tf",["15m"])[0]
            if tf not in _TFOK: tf="15m"
            def _prod():
                try:
                    kl=bget(f"/fapi/v1/klines?symbol={sym}&interval={tf}&limit=500") or []
                    h=[float(k[2]) for k in kl]; l=[float(k[3]) for k in kl]; px=float(kl[-1][4]); n=len(kl); L=5
                    piv=[]
                    for i in range(L,n-L):
                        if h[i]==max(h[i-L:i+L+1]): piv.append(h[i])
                        if l[i]==min(l[i-L:i+L+1]): piv.append(l[i])
                    tol=px*0.004   # cluster 0.4%
                    zones=[]   # [center, count, sum]
                    for pr in sorted(piv):
                        if zones and abs(zones[-1][0]-pr)<=tol:
                            z=zones[-1]; z[1]+=1; z[2]+=pr; z[0]=z[2]/z[1]
                        else: zones.append([pr,1,pr])
                    out=[{"price":round(z[0],1),"touches":z[1],"side":("sup" if z[0]<px else "res")} for z in zones if z[1]>=2]
                    mx=max([o["touches"] for o in out],default=1) or 1
                    for o in out: o["v"]=round(o["touches"]/mx,3)
                    out=sorted(out,key=lambda x:-x["touches"])[:8]
                    return json.dumps({"px":round(px,1),"snr":out})
                except Exception: return json.dumps({"snr":[]})
            return self._s(200,"application/json",cache_get(("snr",sym,tf),60,_prod))
        if path=="/api/calendar":   # kalender ekonomi US (ForexFactory/faireconomy, gratis no-key) — jadwal+forecast+impact; jam dikirim epoch -> frontend konversi WIB
            def _prod():
                import time as _t
                def tier(s,imp):
                    s=s.lower()
                    if any(k in s for k in ("fomc","federal funds","fed chair","powell","cpi","consumer price","non-farm","nonfarm","nfp")): return 3
                    if any(k in s for k in ("pce","ppi","producer price","minutes","adp","jolts","unemployment","retail sales","average hourly")): return 2
                    return 2 if imp=="High" else 1
                def note(s):
                    s=s.lower()
                    if any(k in s for k in ("cpi","pce","ppi","price","inflation")): return "Inflasi: actual > forecast = hawkish -> BTC cenderung TURUN; < forecast = dovish -> NAIK."
                    if any(k in s for k in ("non-farm","nonfarm","nfp","payroll","employ","jobless","unemployment","adp","jolts","hourly earnings")): return "Kerja: jauh lebih KUAT = hawkish -> BTC turun; lebih lemah = dovish -> naik (terlalu lemah = risk-off)."
                    if any(k in s for k in ("fomc","federal funds","fed chair","powell","minutes")): return "Fed: hawkish -> BTC turun; dovish -> naik. Volatil tinggi saat rilis."
                    return "Surprise (actual - forecast) = penggerak; makin jauh = makin volatil (whipsaw 2 arah)."
                # SUMBER = cal_cache.json (ditulis cron cal_fetch.py 1×/jam). Server CUMA baca file
                # -> faireconomy ga ke-hammer dari traffic user -> lolos rate-limit 429.
                ev,fetched=_cal_read()
                # self-heal: kalau file ilang/basi (>3jam, cron mati) -> 1× fetch inline biar ga blank
                if not ev or (int(_t.time())-fetched)>10800:
                    HEAD={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                          "Accept":"application/json,text/plain,*/*","Accept-Language":"en-US,en;q=0.9","Referer":"https://www.forexfactory.com/"}
                    for url in ("https://nfs.faireconomy.media/ff_calendar_thisweek.json","https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json"):
                        try:
                            r=S.get(url,timeout=12,verify=False,headers=HEAD)
                            if r.status_code!=200: continue
                            cur=[]
                            for e in r.json():
                                if e.get("country")!="USD": continue
                                imp=e.get("impact","")
                                if imp not in ("High","Medium"): continue
                                try: ts=int(datetime.datetime.fromisoformat(e.get("date","")).timestamp())
                                except Exception: continue
                                ttl=e.get("title","")
                                cur.append({"t":ts,"title":ttl,"impact":imp,"tier":tier(ttl,imp),"forecast":e.get("forecast") or "","previous":e.get("previous") or "","note":note(ttl)})
                            cur.sort(key=lambda x:x["t"])
                            if cur: _cal_save(cur); ev=cur; break
                        except Exception: continue
                return json.dumps({"events":ev,"now":int(_t.time())})
            return self._s(200,"application/json",cache_get(("calendar",),600,_prod))
        if path=="/api/macro_news":   # berita makro/geopolitik high-impact (perang, Selat Hormuz, sanksi dll) -- Google News RSS keyless
            def _prod():
                import re,urllib.parse as _uq
                q=_uq.quote('(war OR conflict OR sanctions OR "strait of hormuz" OR ceasefire OR missile OR "oil supply") market impact')
                u="https://news.google.com/rss/search?q="+q+"+when:2d&hl=en-US&gl=US&ceid=US:en"
                out=[]
                for url in (u,"https://proxy.cors.sh/"+u):
                    try:
                        t=S.get(url,timeout=12,verify=False,headers={"User-Agent":"Mozilla/5.0"}).text
                        for it in re.findall(r"<item>(.*?)</item>",t,re.S)[:10]:
                            tm=re.search(r"<title>(.*?)</title>",it); pm=re.search(r"<pubDate>(.*?)</pubDate>",it); lm=re.search(r"<link>(.*?)</link>",it)
                            if not tm: continue
                            ti=tm.group(1).replace("&#39;","'").replace("&amp;","&").replace("&quot;",'"').strip()
                            out.append({"title":ti,"pub":pm.group(1) if pm else "","link":lm.group(1) if lm else ""})
                        if out: break
                    except Exception: continue
                return json.dumps(out)
            return self._s(200,"application/json",cache_get(("macronews",),600,_prod))
        if path=="/api/news":
            sym=sym_of(p); lang="id" if parse_qs(p.query).get("lang",[""])[0]=="id" else ""   # normalize -> cegah unbounded cache key
            def _prod():
                tag=NEWSTAG.get(sym,"bitcoin"); out=[]
                try:
                    import xml.etree.ElementTree as ET
                    from email.utils import parsedate_to_datetime
                    r=S.get("https://cointelegraph.com/rss/tag/"+tag,timeout=12,verify=False)
                    root=ET.fromstring(r.content); now=datetime.datetime.now(datetime.timezone.utc)
                    for it in root.findall(".//item")[:10]:
                        t=(it.find("title").text or "").strip(); lk=(it.find("link").text or "").strip()
                        pd=it.find("pubDate"); ago="-"
                        if pd is not None and pd.text:
                            try:
                                mins=int((now-parsedate_to_datetime(pd.text)).total_seconds()/60)
                                ago=(f"{mins}m" if mins<60 else (f"{mins//60}h" if mins<1440 else f"{mins//1440}d"))
                            except: pass
                        de=it.find("description"); summ=""
                        if de is not None and de.text:
                            import re as _re
                            summ=_re.sub("<[^>]+>","",de.text).replace("&nbsp;"," ").strip()[:300]
                        out.append({"title":t,"url":lk,"source":"CoinTelegraph","ago":ago,"summary":summ})
                except Exception: pass
                if not out:   # stale-on-error: RSS gagal -> pakai last-good (jangan blank 120s)
                    with _NEWSLK: return _NEWSLAST.get((sym,lang)) or "[]"
                if lang=="id":   # translate ID (gtx, paralel + cache)
                    try:
                        from concurrent.futures import ThreadPoolExecutor
                        def _tr(n): n["title"]=gtrans(n["title"]); n["summary"]=gtrans(n.get("summary") or ""); return n
                        with ThreadPoolExecutor(max_workers=6) as ex: out=list(ex.map(_tr,out))
                    except Exception: pass
                js=json.dumps(out)
                with _NEWSLK: _NEWSLAST[(sym,lang)]=js
                return js
            return self._s(200,"application/json",cache_get(("news",sym,lang),120,_prod))
        self._s(404,"text/plain","")
class Srv(ThreadingHTTPServer):
    daemon_threads=True            # workers never block process shutdown
    request_queue_size=128         # larger accept backlog for bursty 100+ clients
    _sem=threading.BoundedSemaphore(160)   # S5: cap handler thread konkuren -> tolak kelebihan (anti thread/FD-exhaustion DoS)
    def process_request_thread(self, request, client_address):
        if not self._sem.acquire(blocking=False):
            try: self.shutdown_request(request)
            except Exception: pass
            return
        try: super().process_request_thread(request, client_address)
        finally: self._sem.release()
if __name__=="__main__":
    H.timeout=30                   # per-connection socket timeout -> slow/idle client can't pin a thread forever (slowloris guard)
    print("PUBLIC terminal http://0.0.0.0:8788"); Srv(("0.0.0.0",8788),H).serve_forever()
