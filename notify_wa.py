#!/usr/bin/env python3
"""notify_wa.py — kirim WhatsApp via daemon Baileys lokal (wa-daemon, port 18790).
Daemon harus jalan & sudah scan-QR. Nomor default 6289672845575 (089672845575 +62)."""
import os, sys, requests
WA_PHONE  = os.environ.get("WA_PHONE", "6289672845575")
WA_DAEMON = os.environ.get("WA_DAEMON", "http://127.0.0.1:18790")
def send_whatsapp(text):
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
