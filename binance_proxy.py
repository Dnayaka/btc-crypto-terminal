#!/usr/bin/env python3
"""binance_proxy.py — SOCKS5 lokal yg TEMBUS blokir SNI-DPI ISP ke Binance, TANPA VPN.
Mekanisme: (1) resolve domain via DoH (HTTPS ke 1.1.1.1) -> kebal DNS-hijack ISP;
(2) fragmen byte-1 dari segmen client->upstream PERTAMA (= TLS ClientHello) -> DPI ISP
ga bisa baca SNI "binance" -> ga di-RST. Traffic tetap TLS end-to-end ke Binance
(proxy CUMA forward TCP + split paket pertama -> TIDAK bisa baca isi/API key).

Pakai: jalanin daemon ini (127.0.0.1:1080), arahkan ccxt ke socks5h://127.0.0.1:1080.
NOL pihak-ketiga, NOL VPN. Buat eksekusi order mainnet aman dari penyadapan VPN.

  python3 binance_proxy.py            # listen 127.0.0.1:1080
  python3 binance_proxy.py --selftest # buktiin: ping fapi mainnet lewat proxy
"""
import socket, threading, struct, json, sys, time, urllib.request

LISTEN=("127.0.0.1", 1080)
_DNS={}; _DLK=threading.Lock()

def doh(host):
    """Resolve A-record via Cloudflare DoH (HTTPS) -> IP asli (kebal DNS-hijack ISP). Cache 5 mnt."""
    now=time.time()
    with _DLK:
        e=_DNS.get(host)
        if e and e[1]>now: return e[0]
    try:
        req=urllib.request.Request(f"https://1.1.1.1/dns-query?name={host}&type=A",
                                   headers={"accept":"application/dns-json"})
        d=json.load(urllib.request.urlopen(req,timeout=8))
        ips=[a['data'] for a in d.get('Answer',[]) if a.get('type')==1]
        if ips:
            with _DLK: _DNS[host]=(ips[0], now+300)
            return ips[0]
    except Exception: pass
    return None

def pipe(src, dst, fragment_first):
    """Relay src->dst. Kalau fragment_first: split kiriman PERTAMA jadi byte-1 + sisanya (desync DPI)."""
    first=True
    try:
        while True:
            data=src.recv(65536)
            if not data: break
            if first and fragment_first and len(data)>2:
                dst.sendall(data[:1]); time.sleep(0.02); dst.sendall(data[1:])   # fragmen ClientHello
            else:
                dst.sendall(data)
            first=False
    except Exception: pass
    finally:
        for s in (src,dst):
            try: s.shutdown(socket.SHUT_RDWR)
            except Exception: pass

def handle(c):
    try:
        c.settimeout(20)
        # --- SOCKS5 greeting ---
        v=c.recv(2)
        if len(v)<2 or v[0]!=5: return
        nm=v[1]; c.recv(nm); c.sendall(b"\x05\x00")            # no-auth
        # --- request ---
        hdr=c.recv(4)
        if len(hdr)<4 or hdr[1]!=1: c.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00"); return  # CONNECT only
        atyp=hdr[3]
        if atyp==1:   host=socket.inet_ntoa(c.recv(4)); dom=None
        elif atyp==3: ln=c.recv(1)[0]; dom=c.recv(ln).decode(); host=dom
        elif atyp==4: host=socket.inet_ntop(socket.AF_INET6,c.recv(16)); dom=None
        else: c.sendall(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00"); return
        port=struct.unpack(">H", c.recv(2))[0]
        # resolve via DoH kalau domain (kebal DNS-hijack)
        ip=doh(dom) if dom else host
        if not ip:
            try: ip=socket.gethostbyname(host)
            except Exception: c.sendall(b"\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00"); return
        up=socket.socket(); up.settimeout(20)
        try: up.connect((ip,port))
        except Exception: c.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00"); return
        c.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")   # success
        frag = (port==443)                                       # fragmen cuma TLS (ClientHello)
        t1=threading.Thread(target=pipe,args=(c,up,frag),daemon=True)
        t2=threading.Thread(target=pipe,args=(up,c,False),daemon=True)
        t1.start(); t2.start(); t1.join(); t2.join()
    except Exception: pass
    finally:
        try: c.close()
        except Exception: pass

def serve():
    srv=socket.socket(); srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    srv.bind(LISTEN); srv.listen(128)
    print(f"binance-proxy SOCKS5 (DoH + anti-DPI) -> {LISTEN[0]}:{LISTEN[1]}  | ccxt: socks5h://{LISTEN[0]}:{LISTEN[1]}")
    while True:
        c,_=srv.accept(); threading.Thread(target=handle,args=(c,),daemon=True).start()

def selftest():
    th=threading.Thread(target=serve,daemon=True); th.start(); time.sleep(0.5)
    import urllib.request
    try:
        import socks  # PySocks
    except Exception:
        print("PySocks belum ada (pip install pysocks) — tes via curl manual"); return
    for tag,host in (("fapi","fapi.binance.com"),("api","api.binance.com")):
        s=socket.socket(); s.settimeout(12)
        try:
            import socks as _sk
            sk=_sk.socksocket(); sk.set_proxy(_sk.SOCKS5,"127.0.0.1",1080,rdns=True); sk.settimeout(12)
            sk.connect((host,443))
            import ssl as _ssl; ctx=_ssl.create_default_context(); ss=ctx.wrap_socket(sk,server_hostname=host)
            ss.sendall(f"GET /{'fapi' if tag=='fapi' else 'api'}/v{'1' if tag=='fapi' else '3'}/ping HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
            line=ss.recv(200).split(b"\r\n")[0].decode(errors="ignore")
            print(f"  {host} via proxy -> {line}")
        except Exception as e: print(f"  {host} via proxy -> GAGAL {type(e).__name__}: {str(e)[:50]}")

if __name__=="__main__":
    if "--selftest" in sys.argv: selftest()
    else: serve()
