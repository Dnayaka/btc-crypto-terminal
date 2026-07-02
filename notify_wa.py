#!/usr/bin/env python3
"""notify_wa.py — kirim WhatsApp via daemon Baileys lokal (wa-daemon, port 18790).
Daemon harus jalan & sudah scan-QR. Nomor tujuan: env WA_PHONE, atau field "wa_phone" di
bot_secrets.json (gitignored), atau kosong (fitur no-op sampai diisi lewat admin panel)."""
import os, sys, json, requests
_HERE = os.path.dirname(os.path.abspath(__file__))
_CFG = os.path.join(_HERE, "bot_config.json")
_SECF = os.path.join(_HERE, "bot_secrets.json")
def _wa_phone():
    if os.environ.get("WA_PHONE"): return os.environ["WA_PHONE"]
    try: return json.load(open(_SECF)).get("wa_phone", "")
    except Exception: return ""
WA_PHONE  = _wa_phone()
WA_DAEMON = os.environ.get("WA_DAEMON", "http://127.0.0.1:18790")
def wa_enabled():
    """Fitur WhatsApp ON/OFF dari bot_config.json (default OFF). Bisa di-toggle di admin :8789."""
    try: return bool(json.load(open(_CFG)).get("wa_enabled", False)) and bool(WA_PHONE)
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
