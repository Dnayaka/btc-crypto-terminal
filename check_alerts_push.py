#!/usr/bin/env python3
"""check_alerts_push.py — cron (tiap ±2 menit): cek semua alert price/RSI aktif lintas user,
kirim WEB PUSH (browser, TANPA WhatsApp) kalau kena. Beda dari checkAlerts() di browser (yg cuma
jalan selama tab kebuka) -- ini server-side, jalan walau tab ketutup/HP terkunci, asal user udah
"Aktifkan notifikasi push" di web (subscription tersimpan push_subs.json).

Sekali kena -> alert di-nonaktifkan (one-shot, sama kayak checkAlerts() client-side, hindari duplikat
notif dari 2 jalur sekaligus). Kalau user PUNYA push subscription: server yg kirim. Kalau TIDAK: alert
tetap nonaktif pas kena, browser client-side checkAlerts() juga bakal lihatnya udah inactive (no-op).
"""
import os, sys, json, time
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bot_v20_funding import bget
from eng import rsi as _rsi

ALERTS_F=os.path.join(HERE,"alerts.json")
PUSHSUB_F=os.path.join(HERE,"push_subs.json")
VAPID_F=os.path.join(HERE,"vapid_keys.json")
SYM_LABEL={"BTCUSDT":"BTC","ETHUSDT":"ETH","SOLUSDT":"SOL"}

def _load(path):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return {}

def _save_atomic(path, d):
    tmp=path+".tmp"
    fd=os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
    with os.fdopen(fd,"w") as f: json.dump(d,f)
    os.replace(tmp, path)

def _fetch_metric(sym, kind):
    try:
        if kind=="price":
            j=bget(f"/fapi/v1/premiumIndex?symbol={sym}") or {}
            return float(j.get("markPrice",0)) or None
        else:   # rsi -- 15m, sama TF yg ditampilkan di web
            kl=bget(f"/fapi/v1/klines?symbol={sym}&interval=15m&limit=100") or []
            if len(kl)<20: return None
            closes=[float(k[4]) for k in kl]
            r=_rsi(closes,14)
            return float(r[-1]) if r is not None and len(r) else None
    except Exception as e:
        print(f"  fetch gagal {sym}/{kind}: {str(e)[:60]}"); return None

def main():
    alerts=_load(ALERTS_F)
    if not alerts: print("nggak ada alert tersimpan, skip."); return
    subs=_load(PUSHSUB_F)
    vapid=_load(VAPID_F)
    has_push = bool(vapid.get("private_pem"))
    if has_push:
        from pywebpush import webpush, WebPushException

    cache={}   # {(sym,kind): value} -- 1x fetch per kombinasi per run, dipakai user manapun
    changed=False; n_hit=0; n_pushed=0

    for user, rules in list(alerts.items()):
        active=[a for a in rules if a.get("active")]
        if not active: continue
        for a in active:
            sym=a.get("sym","BTCUSDT"); kind=a.get("type","price")
            key=(sym,kind)
            if key not in cache: cache[key]=_fetch_metric(sym,kind)
            val=cache[key]
            if val is None: continue
            hit = (val<=a["value"]) if a.get("op")=="<=" else (val>=a["value"])
            if not hit: continue
            a["active"]=False; a["triggered_at"]=int(time.time()); changed=True; n_hit+=1
            label=SYM_LABEL.get(sym,sym)
            metric_txt=f"RSI(15m) {val:.1f}" if kind=="rsi" else f"harga ${val:,.1f}"
            op_txt="≤" if a.get("op")=="<=" else "≥"
            title=f"🔔 {label} alert kena"
            body=f"{metric_txt} ({op_txt} {a['value']})"
            print(f"  KENA: user={user} {label} {metric_txt} {op_txt} {a['value']}")
            if not has_push: continue
            for sub in list(subs.get(user,[])):
                try:
                    webpush(subscription_info=sub,
                            data=json.dumps({"title":title,"body":body,"tag":f"alert-{a.get('id','')}"}),
                            vapid_private_key=vapid["private_pem"],
                            vapid_claims={"sub":"mailto:noreply@dnayaka.local"})
                    n_pushed+=1
                except WebPushException as e:
                    code=getattr(getattr(e,"response",None),"status_code",None)
                    if code in (404,410):   # subscription expired/invalid -> buang, jangan retry selamanya
                        subs[user]=[s for s in subs.get(user,[]) if s.get("endpoint")!=sub.get("endpoint")]
                        print(f"    subscription expired (user={user}), dibuang")
                    else:
                        print(f"    webpush gagal (user={user}): {str(e)[:80]}")
                except Exception as e:
                    print(f"    webpush error (user={user}): {str(e)[:80]}")
    if changed:
        _save_atomic(ALERTS_F, alerts)
        _save_atomic(PUSHSUB_F, subs)
    print(f"selesai: {n_hit} alert kena, {n_pushed} push terkirim.")

if __name__=="__main__": main()
