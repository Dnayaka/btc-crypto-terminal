#!/usr/bin/env python3
"""fed_summary.py — rangkuman AI event The Fed (hawkish/dovish + terjemahan ID).
Cron: cek cal_cache.json; kalau ADA event Fed yg BARU LEWAT (<=36 jam) -> ambil berita Google News (keyless)
-> Gemini simpulkan {tone hawkish/dovish/netral, poin[3 ID], efek_btc} -> tulis fed_summary.json.
config_server.py PUBLIK cuma BACA file (/api/fed, NOL key). Pola sama ai_gen.py -> ai_read.json.

  python3 fed_summary.py           # generate (cron)
  python3 fed_summary.py --force   # abaikan gate waktu (tes: pakai event Fed terdekat)
Analisa/komentar saja, BUKAN sinyal trade."""
import os, sys, json, time, re, requests, urllib.parse, urllib3
urllib3.disable_warnings()
from gemini import call_gemini, extract_json, gemini_key
from ai_gen import build_context   # reuse: DXY/dominance/funding dari endpoint lokal SENDIRI (sudah di-cache
                                    # server-side TTL masing2) -> panggil di sini GRATIS, tanpa fetch ulang ke Yahoo/CoinGecko

HERE = "/home/dnayaka/Documents/dynamic_rsi/btc-terminal"
CAL  = os.path.join(HERE, "cal_cache.json")
OUT  = os.path.join(HERE, "fed_summary.json")
VERIFY = os.environ.get("FETCH_VERIFY","0")=="1"
H = {"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36"}
FED_RE = re.compile(r"fomc|fed chair|federal funds|federal reserve|powell|warsh|fed minutes|interest rate|monetary policy", re.I)

def pick_fed_event(force=False):
    """Event Fed yg baru lewat <=36 jam (terbaru). force=True -> event Fed terdekat apa pun (buat tes)."""
    try: ev = json.load(open(CAL)).get("events", [])
    except Exception: return None
    now = int(time.time()); best = None
    fed = [e for e in ev if FED_RE.search(e.get("title",""))]
    if not fed: return None
    if force:
        return min(fed, key=lambda e: abs(e["t"]-now))
    # window [-36 jam .. +48 jam]: jelang event = preview sentimen berita, setelah = rangkuman yg disampaikan.
    for e in fed:
        dt = e["t"] - now
        if -36*3600 <= dt <= 48*3600:
            if best is None or abs(dt) < abs(best["t"]-now): best = e
    return best

def fetch_fed_news(n=8):
    q = urllib.parse.quote('"Federal Reserve" interest rate OR monetary OR FOMC OR hawkish OR dovish')
    u = "https://news.google.com/rss/search?q=" + q + "+when:3d&hl=en-US&gl=US&ceid=US:en"
    for url in (u, "https://proxy.cors.sh/"+u):
        try:
            t = requests.get(url, timeout=12, verify=VERIFY, headers=H).text
            out = []
            for it in re.findall(r"<item>(.*?)</item>", t, re.S):
                m = re.search(r"<title>(.*?)</title>", it)
                if not m: continue
                ti = m.group(1).replace("&#39;","'").replace("&amp;","&").replace("&quot;",'"').strip()
                if re.search(r"fed|reserve|fomc|rate|powell|warsh|monetary|hawkish|dovish|inflation", ti, re.I):
                    out.append(ti)
                if len(out) >= n: break
            if out: return out
        except Exception: continue
    return []

# prompt Gemini (dirakit via concatenation, ev/news/ctx di-sisipkan aman)
_P1 = ('Kamu analis makro-ekonomi. Di bawah ini judul-judul berita TERBARU soal The Fed (bank sentral AS), '
       'terkait event "')
_P2 = ('". Simpulkan sikap The Fed. Balas HANYA JSON valid:\n'
       '{"tone":"<hawkish|dovish|netral>",'
       '"tone_id":"<arti singkat Bahasa Indonesia: hawkish=cenderung ketat/pertahankan-naikkan bunga; '
       'dovish=longgar/turunkan bunga; netral=belum jelas>",'
       '"poin":["<poin 1 ringkas Bahasa Indonesia>","<poin 2>","<poin 3>"],'
       '"efek_btc":"<1 kalimat efek ke BTC, cross-check dgn data pasar TERKINI di bawah (mis. DXY sudah naik = konfirmasi hawkish)>"}\n'
       'Aturan: Bahasa Indonesia, ringkas, faktual, NETRAL, JANGAN saran beli/jual/leverage. '
       'Kalau berita tidak cukup jelas, tone="netral".\nBERITA:\n- ')
_P3 = '\n\nDATA PASAR TERKINI (faktor eksternal, buat cross-check bukan sumber utama):\n'

def build_prompt(ev_title, news, ctx=None):
    tail = ""
    if ctx:
        keep = {k: ctx[k] for k in ("price","funding_pct","dxy_index","dxy_chg_24h_pct","dxy_chg_30d_pct",
                                     "btc_dominance_pct","fear_greed") if ctx.get(k) is not None}
        if keep: tail = _P3 + json.dumps(keep, ensure_ascii=False)
    return _P1 + ev_title + _P2 + "\n- ".join(news[:8]) + tail + "\n"

def save(d):
    tmp = OUT + ".tmp"; json.dump(d, open(tmp,"w"), ensure_ascii=False, indent=1); os.replace(tmp, OUT)

def generate(force=False):
    ev = pick_fed_event(force=force)
    if not ev:
        save({"active":False,"ts":int(time.time())}); print("tidak ada event Fed baru lewat"); return
    # THROTTLE: cron jalan tiap 15mnt (biar auto-fetch sendiri, ga perlu --force manual), tapi Gemini/news
    # cuma DIPANGGIL kalau perlu -> event sama & belum lewat gap-minimum di-skip (hemat kuota Gemini).
    # "panas" (dalam +-3jam dr mulai) = refresh tiap 15mnt; jauh dari itu = tiap 1 jam cukup.
    if not force:
        prev = {}
        try: prev = json.load(open(OUT))
        except Exception: pass
        now = int(time.time())
        hot = abs(ev["t"] - now) <= 3*3600
        min_gap = 15*60 if hot else 60*60
        if prev.get("event") == ev["title"] and (now - prev.get("ts", 0)) < min_gap:
            print(f"skip (event sama, {'panas' if hot else 'jauh'}, gap<{min_gap//60}mnt): {ev['title']}"); return
    if not gemini_key():
        save({"active":False,"reason":"no_gemini_key","ts":int(time.time())}); print("no gemini key"); return
    news = fetch_fed_news()
    if not news:
        save({"active":False,"reason":"no_news","ts":int(time.time())}); print("berita Fed kosong"); return
    ctx = build_context()   # reuse ai_gen: DXY/dominance/funding/fear-greed dari endpoint lokal (cached, gratis)
    txt, err = call_gemini(build_prompt(ev["title"], news, ctx), max_tokens=500)
    data = extract_json(txt) if txt else None
    if not data:
        save({"active":False,"reason":err or "parse_fail","ts":int(time.time())}); print("gemini gagal:", err or "parse_fail"); return
    tone = str(data.get("tone","netral")).lower()
    if tone not in ("hawkish","dovish","netral"): tone = "netral"
    out = {"active":True, "ts":int(time.time()), "event":ev["title"], "event_t":ev["t"],
           "tone":tone, "tone_id":data.get("tone_id",""),
           "poin":[x for x in data.get("poin",[]) if x][:3], "efek_btc":data.get("efek_btc",""),
           "headlines":news[:5],
           "dxy_index":ctx.get("dxy_index"),"dxy_chg_24h_pct":ctx.get("dxy_chg_24h_pct"),"btc_dominance_pct":ctx.get("btc_dominance_pct")}
    save(out); print("fed_summary.json:", tone, "|", ev["title"], "|", len(out["poin"]), "poin")

if __name__ == "__main__":
    generate(force=("--force" in sys.argv))
