#!/usr/bin/env python3
"""notify_wa.py — kirim WhatsApp via daemon Baileys lokal (wa-daemon, port 18790).
Daemon harus jalan & sudah scan-QR. Nomor default 6289672845575 (089672845575 +62)."""
import os, sys, json, requests
WA_PHONE  = os.environ.get("WA_PHONE", "6289672845575")
WA_DAEMON = os.environ.get("WA_DAEMON", "http://127.0.0.1:18790")
_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_config.json")
def wa_enabled():
    """Fitur WhatsApp ON/OFF dari bot_config.json (default OFF). Bisa di-toggle di admin :8789."""
    try: return bool(json.load(open(_CFG)).get("wa_enabled", False))
    except Exception: return False
def send_whatsapp(text):
    if not wa_enabled():
        print("[WA] dimatikan (wa_enabled=false) — nyalakan di admin"); return False
    try:
        r=requests.post(WA_DAEMON+"/send",json={"to":WA_PHONE,"message":text},timeout=20)
        j=r.json(); ok=j.get("ok")
        print(f"[WA] -> {WA_PHONE}: {'OK' if ok else 'GAGAL '+str(j)[:80]}")
        return ok
    except Exception as e:
        print("[WA] daemon belum jalan/terhubung:",str(e)[:80]); return False
if __name__=="__main__":
    msg=" ".join(sys.argv[1:]) or "Tes notifikasi bot trading BTC ✅"
    # cek status daemon dulu
    try:
        st=requests.get(WA_DAEMON+"/status",timeout=5).json()
        print("[WA] daemon status: terhubung =",st.get("connected"))
    except Exception as e: print("[WA] daemon TIDAK jalan:",str(e)[:60])
    send_whatsapp(msg)
