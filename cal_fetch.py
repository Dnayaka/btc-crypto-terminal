#!/usr/bin/env python3
"""Cron fetcher kalender ekonomi US (ForexFactory via faireconomy).
Jalan terjadwal (cron) -> tulis cal_cache.json. Server config_server.py CUMA baca file ini
(decouple dari traffic user -> faireconomy ga ke-hammer -> lolos rate-limit 429).
Pola sama: btc15m.py->btc_v20.json, ai_gen.py->ai_read.json."""
import urllib.request, urllib.parse, ssl, json, re, datetime, time, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CALPATH = os.path.join(HERE, "cal_cache.json")
BLSPATH = os.path.join(HERE, "econ_bls.json")   # cache actual BLS (limit keyless 25/hari -> refetch max tiap 3 jam)
ADPPATH = os.path.join(HERE, "adp_actual.json")  # cache actual ADP (Google News, beda sumber dari BLS)
URLS = ["https://nfs.faireconomy.media/ff_calendar_thisweek.json",
        "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json"]
HEAD = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "application/json,text/plain,*/*", "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.forexfactory.com/"}
_CTX = ssl.create_default_context(); _CTX.check_hostname = False; _CTX.verify_mode = ssl.CERT_NONE

def tier(s, imp):
    s = s.lower()
    if any(k in s for k in ("fomc", "federal funds", "fed chair", "powell", "cpi", "consumer price", "non-farm", "nonfarm", "nfp")): return 3
    if any(k in s for k in ("pce", "ppi", "producer price", "minutes", "adp", "jolts", "unemployment", "retail sales", "average hourly")): return 2
    return 2 if imp == "High" else 1

def note(s):
    s = s.lower()
    if any(k in s for k in ("cpi", "pce", "ppi", "price", "inflation")): return "Inflasi: actual > forecast = hawkish -> BTC cenderung TURUN; < forecast = dovish -> NAIK."
    if any(k in s for k in ("non-farm", "nonfarm", "nfp", "payroll", "employ", "jobless", "unemployment", "adp", "jolts", "hourly earnings")): return "Kerja: jauh lebih KUAT = hawkish -> BTC turun; lebih lemah = dovish -> naik (terlalu lemah = risk-off)."
    if any(k in s for k in ("fomc", "federal funds", "fed chair", "powell", "minutes")): return "Fed: hawkish -> BTC turun; dovish -> naik. Volatil tinggi saat rilis."
    return "Surprise (actual - forecast) = penggerak; makin jauh = makin volatil (whipsaw 2 arah)."

# ===== ACTUAL (hasil rilis) via BLS public API (keyless). faireconomy TAK kasih actual. =====
BLS_SERIES = ["CUUR0000SA0","CUUR0000SA0L1E","LNS14000000","CES0000000001","CES0500000003","WPUFD49207","JTS000000000000000JOL"]
def _flist(seq, key=None):
    """List float, skip nilai non-numerik ('-'/''/None) — BLS & DBnomics kadang ada placeholder."""
    out = []
    for x in seq:
        v = x[key] if key else x
        try: out.append(float(v))
        except (ValueError, TypeError): pass
    return out

def _econ_compute(sv):
    """sv = {series_id: [nilai float, NEWEST-first]} -> dict indikator. Dipakai BLS & DBnomics (sumber sama-formatnya)."""
    def g(sid): return sv.get(sid) or []
    def mom(d): return (d[0]/d[1]-1)*100
    out = {}
    cpi = g("CUUR0000SA0")
    if len(cpi) >= 2: out["cpi_mom"] = round(mom(cpi),1)
    if len(cpi) >= 13: out["cpi_yoy"] = round((cpi[0]/cpi[12]-1)*100,1)
    cc = g("CUUR0000SA0L1E")
    if len(cc) >= 2: out["ccpi_mom"] = round(mom(cc),1)
    ur = g("LNS14000000")
    if ur: out["unemp"] = round(ur[0],1)
    nf = g("CES0000000001")
    if len(nf) >= 2: out["nfp"] = int(round(nf[0]-nf[1]))
    ah = g("CES0500000003")
    if len(ah) >= 2: out["ahe_mom"] = round(mom(ah),1)
    pp = g("WPUFD49207")
    if len(pp) >= 2: out["ppi_mom"] = round(mom(pp),1)
    jo = g("JTS000000000000000JOL")
    if jo: out["jolts"] = round(jo[0]/1000.0, 2)   # ribuan -> juta
    return out

def fetch_bls():
    """PRIMARY: BLS public API (keyless, 25 query/hari)."""
    try:
        yr = datetime.datetime.now().year
        body = json.dumps({"seriesid": BLS_SERIES, "startyear": str(yr-1), "endyear": str(yr)}).encode()
        req = urllib.request.Request("https://api.bls.gov/publicAPI/v2/timeseries/data/", data=body, headers={"Content-Type":"application/json"})
        j = json.load(urllib.request.urlopen(req, context=_CTX, timeout=15))
        if j.get("status") != "REQUEST_SUCCEEDED": return {}
        raw = {s["seriesID"]: s["data"] for s in j.get("Results",{}).get("series",[])}
    except Exception as ex:
        sys.stderr.write("[cal_fetch] BLS %s: %s\n" % (type(ex).__name__, str(ex)[:80])); return {}
    sv = {sid: _flist(d, "value") for sid, d in raw.items()}   # BLS data = NEWEST-first
    out = _econ_compute(sv)
    cpi = raw.get("CUUR0000SA0")
    if cpi: out["period"] = cpi[0]["periodName"] + " " + cpi[0]["year"]
    if out: out["src"] = "BLS"
    return out

def fetch_dbnomics():
    """BACKUP: DBnomics (keyless, mirror BLS) kalau BLS mati/limit."""
    DS = {"CUUR0000SA0":"cu","CUUR0000SA0L1E":"cu","LNS14000000":"ln","CES0000000001":"ce","CES0500000003":"ce","WPUFD49207":"wp","JTS000000000000000JOL":"jt"}
    sv = {}
    for sid, ds in DS.items():
        base = "https://api.db.nomics.world/v22/series/BLS/%s/%s?observations=1" % (ds, sid)
        for url in (base, "https://proxy.cors.sh/" + base):
            try:
                req = urllib.request.Request(url, headers=HEAD)
                docs = json.load(urllib.request.urlopen(req, context=_CTX, timeout=8))["series"]["docs"][0]
                vals = _flist(docs["value"])   # DBnomics = OLDEST-first
                if vals: sv[sid] = vals[::-1]   # -> NEWEST-first
                break
            except Exception: continue
    if not sv:
        sys.stderr.write("[cal_fetch] DBnomics backup juga gagal\n"); return {}
    out = _econ_compute(sv)
    if out: out["src"] = "DBnomics"
    return out

def load_bls():
    """Cache 3-jam (hemat kuota). PRIMARY BLS -> BACKUP DBnomics -> stale cache."""
    try:
        c = json.load(open(BLSPATH))
        if int(time.time()) - c.get("ts",0) < 3*3600 and c.get("data"): return c["data"]
    except Exception: pass
    d = fetch_bls() or fetch_dbnomics()   # backup provider kalau primary mati
    if d:
        try:
            fd = os.open(BLSPATH + ".tmp", os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
            with os.fdopen(fd, "w") as f: json.dump({"ts": int(time.time()), "data": d}, f)
            os.replace(BLSPATH + ".tmp", BLSPATH)
        except Exception: pass
        return d
    try: return json.load(open(BLSPATH)).get("data",{})   # fallback stale
    except Exception: return {}

def bls_actual(title, b):
    """Format nilai actual sesuai judul event (BLS cuma cover indikator utama)."""
    t = title.lower()
    if any(k in t for k in ("cpi","consumer price")):
        if "y/y" in t and "cpi_yoy" in b: return "%.1f%%" % b["cpi_yoy"]
        if "core" in t and "ccpi_mom" in b: return "%+.1f%%" % b["ccpi_mom"]
        if "cpi_mom" in b: return "%+.1f%%" % b["cpi_mom"]
    if "unemployment rate" in t and "unemp" in b: return "%.1f%%" % b["unemp"]
    if any(k in t for k in ("non-farm","nonfarm","nfp")) and "adp" not in t and "nfp" in b: return ("%+d" % b["nfp"]) + "K"
    if "average hourly earnings" in t and "ahe_mom" in b: return "%+.1f%%" % b["ahe_mom"]
    if any(k in t for k in ("ppi","producer price")) and "ppi_mom" in b: return "%+.1f%%" % b["ppi_mom"]
    if any(k in t for k in ("jolts","job openings")) and "jolts" in b: return "%.2fM" % b["jolts"]
    return ""

# ===== ADP actual (BEDA sumber dari BLS -- ADP = survei swasta, angkanya sendiri).
# BLS ga punya data ini; ambil dari rilis pers ADP via Google News RSS (keyless). =====
_ADP_NUM_RE = re.compile(r"(increas\w*|decreas\w*|rose|fell|dropped|declin\w*)\s+(?:by\s+)?([\d,]{2,7})\s*(?:jobs)?", re.I)
_ADP_NEG = ("decreased","decreasing","fell","dropped","declined","declining")

def fetch_adp_actual():
    """Cari angka ADP National Employment Report TERBARU dari judul berita (PR Newswire/Reuters/CNBC dll,
    semua ngutip angka sama dari rilis pers ADP -> regex robust). Cache 3-jam (mirip BLS, sopan ke Google News)."""
    try:
        c = json.load(open(ADPPATH))
        if int(time.time()) - c.get("ts", 0) < 3*3600 and c.get("value"): return c["value"]
    except Exception: pass
    q = urllib.parse.quote('"ADP National Employment Report" OR "ADP employment"')
    u = "https://news.google.com/rss/search?q=" + q + "+when:4d&hl=en-US&gl=US&ceid=US:en"
    val = ""
    for url in (u, "https://proxy.cors.sh/"+u):
        try:
            req = urllib.request.Request(url, headers=HEAD)
            t = urllib.request.urlopen(req, context=_CTX, timeout=12).read().decode("utf-8", "ignore")
            for it in re.findall(r"<title>(.*?)</title>", t):
                m = _ADP_NUM_RE.search(it)
                if not m: continue
                num = int(m.group(2).replace(",", ""))   # angka mentah jobs (mis. 98,000)
                neg = m.group(1).lower() in _ADP_NEG
                val = ("-" if neg else "+") + str(round(num/1000)) + "K"   # skala samain ke forecast ("118K")
                break
            if val: break
        except Exception as ex:
            sys.stderr.write("[cal_fetch] ADP news %s: %s\n" % (type(ex).__name__, str(ex)[:80]))
    if val:
        try:
            fd = os.open(ADPPATH + ".tmp", os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
            with os.fdopen(fd, "w") as f: json.dump({"ts": int(time.time()), "value": val}, f)
            os.replace(ADPPATH + ".tmp", ADPPATH)
        except Exception: pass
        return val
    try: return json.load(open(ADPPATH)).get("value", "")   # fallback stale
    except Exception: return ""

def fetch():
    for attempt in range(4):
        for url in URLS:
            try:
                req = urllib.request.Request(url, headers=HEAD)
                data = json.load(urllib.request.urlopen(req, context=_CTX, timeout=15))
                ev = []
                for e in data:
                    if e.get("country") != "USD": continue
                    imp = e.get("impact", "")
                    if imp not in ("High", "Medium"): continue
                    try: ts = int(datetime.datetime.fromisoformat(e.get("date", "")).timestamp())
                    except Exception: continue
                    ttl = e.get("title", "")
                    ev.append({"t": ts, "title": ttl, "impact": imp, "tier": tier(ttl, imp),
                               "forecast": e.get("forecast") or "", "previous": e.get("previous") or "",
                               "actual": e.get("actual") or "", "note": note(ttl)})
                ev.sort(key=lambda x: x["t"])
                return ev
            except Exception as ex:
                sys.stderr.write("[cal_fetch] %s %s: %s\n" % (url, type(ex).__name__, str(ex)[:80]))
        time.sleep(8)   # tunggu window ban faireconomy (429 bertahan menit-an)
    return None

def main():
    ev = fetch()
    if ev is None:
        sys.stderr.write("[cal_fetch] semua attempt gagal -> file lama dipertahankan\n")
        sys.exit(1)
    # tempel ACTUAL (hasil rilis) ke event yang SUDAH lewat, dari BLS
    b = load_bls(); now = int(time.time()); nact = 0
    try: bls_ts = json.load(open(BLSPATH)).get("ts", 0)
    except Exception: bls_ts = 0
    for e in ev:
        # tempel HANYA kalau event sudah lewat DAN BLS di-fetch SETELAH event (biar dapat angka bulan baru, bukan sisa bulan lama)
        if e["t"] <= now and bls_ts >= e["t"] and not e.get("actual"):
            a = bls_actual(e["title"], b)
            if a: e["actual"] = a; nact += 1
    # ADP (sumber TERPISAH dari BLS, survei swasta) -- cek event ADP yg baru lewat (<=6 jam, rilis pers biasanya cepat)
    nadp = 0
    for e in ev:
        if "adp" in e["title"].lower() and 0 <= now - e["t"] <= 6*3600 and not e.get("actual"):
            a = fetch_adp_actual()
            if a: e["actual"] = a; nadp += 1
    payload = {"events": ev, "fetched": int(time.time()), "bls_period": b.get("period","")}
    fd = os.open(CALPATH + ".tmp", os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
    with os.fdopen(fd, "w") as f: json.dump(payload, f)
    os.replace(CALPATH + ".tmp", CALPATH)
    print("[cal_fetch] OK %d event (%d actual dari %s + %d dari ADP-news, period %s) -> %s" % (len(ev), nact, b.get("src","-"), nadp, b.get("period","-"), CALPATH))

if __name__ == "__main__":
    main()
