#!/usr/bin/env python3
"""ai_gen.py — generator komentar AI (cron, sisi PRIVAT). Ambil data pasar dari endpoint
terminal publik sendiri (localhost:8788), minta Gemini bikin: (1) komentar pasar 2-3 kalimat,
(2) ringkasan berita 2-3 bullet. Tulis ke ai_read.json -> dibaca terminal publik (tanpa key).

PEMAKAIAN:
  python3 ai_gen.py --once     # generate sekali (cron tiap 15-30m)
  python3 ai_gen.py --mock     # tes pipeline tanpa call Gemini (canned response)
  cron:  5,35 * * * *  cd .../btc-terminal && python3 ai_gen.py --once >> ai_gen.log 2>&1

⚠️ Output AI = analisa/komentar saja, BUKAN sinyal trade. Terpisah total dari bot."""
import os, sys, json, time, argparse, requests, urllib3
urllib3.disable_warnings()
from gemini import call_gemini, extract_json, gemini_key

HERE = "/home/dnayaka/Documents/dynamic_rsi/btc-terminal"
OUT  = os.path.join(HERE, "ai_read.json")
PUB  = "http://localhost:8788"
VERIFY = os.environ.get("FETCH_VERIFY","0")=="1"

def _load_pass():   # S2: env > file .terminal_pass (no hardcode)
    p=os.environ.get("TERMINAL_PASS")
    if p: return p
    try:
        with open(os.path.join(HERE,".terminal_pass")) as f: return f.read().strip()
    except Exception: return ""
PASS=_load_pass()   # :8788 gated -> kirim auth ke localhost
def _get(path):
    try: return requests.get(PUB+path, timeout=10, verify=VERIFY, auth=("t",PASS)).json()
    except Exception: return {}

def build_context():
    """Rangkai snapshot pasar dari endpoint publik SENDIRI (sudah agregasi Binance/news/global/dxy,
    semua ke-cache server-side dgn TTL sendiri -> panggil ini berkali2 dari script manapun itu GRATIS,
    ga nambah beban ke Yahoo/CoinGecko/Binance). Dipakai ai_gen.py (komentar umum) & fed_summary.py
    (rangkuman Fed, reuse biar ga duplikat fetch-logic utk faktor eksternal yg sama)."""
    m=_get("/api/metrics"); l=_get("/api/liquidity"); g=_get("/api/global")
    st=_get("/api/stats"); nw=_get("/api/news"); dx=_get("/api/dxy")
    news=[n.get("title","") for n in (nw if isinstance(nw,list) else [])][:8]
    ctx={
        "price": m.get("mark"), "funding_pct": m.get("funding"),
        "fear_greed": m.get("fng"), "fng_txt": m.get("fng_txt"),
        "change_24h_pct": st.get("change"), "high_24h": st.get("high"), "low_24h": st.get("low"),
        "oi": l.get("oi"), "retail_long_short": l.get("ls"), "WHALE_long_short_top_trader": l.get("top"),
        "taker_buy_sell": l.get("taker"), "bidask_imbalance": l.get("imb"),
        "btc_dominance_pct": g.get("dom"), "total_mcap_t": g.get("mcap"), "mcap_chg_24h": g.get("mcapch"),
        "dxy_index": dx.get("last"), "dxy_chg_24h_pct": dx.get("chg"), "dxy_chg_30d_pct": dx.get("chg30"),
        "news_titles": news,
    }
    return ctx

P_INTRO = "Kamu analis pasar kripto. Berdasarkan data BTC perpetual berikut, balas HANYA JSON valid:\n"
SCHEMA_HEAD = ('{"commentary": "<2-3 kalimat: momentum, funding, posisi vs 24h range, yang diwaspadai; '
               'sebut dxy_index/dominance HANYA kalau pergerakannya cukup besar & relevan>",\n'
               '  "whale": "<1 kalimat: WHALE (top trader L/S) condong LONG/SHORT, vs RITEL (retail L/S) & taker buy/sell — siapa lawan siapa>",\n'
               '  "bias": "<bullish|bearish|netral>"')
NEWS_FIELD = ',\n  "news": ["<ringkas 1>", "<ringkas 2>", "<ringkas 3>"]'
P_MID = "\n\nAturan: bahasa Indonesia, ringkas, faktual, NETRAL. JANGAN kasih saran beli/jual/leverage. Cuma observasi.\nDATA:\n"

def build_prompt(ctx, with_news):
    schema = SCHEMA_HEAD + (NEWS_FIELD if with_news else "") + "}"
    data = json.dumps({k:v for k,v in ctx.items() if k!="news_titles"}, ensure_ascii=False)
    newsline = ("\nBERITA (judul): " + " | ".join(ctx["news_titles"][:6])) if with_news else ""
    return P_INTRO + schema + P_MID + data + newsline + "\n"

def _news_hash(titles):
    import hashlib
    return hashlib.md5(("|".join(titles or [])).encode("utf-8")).hexdigest()

def generate(mock=False):
    ctx=build_context(); prev=load()
    nh=_news_hash(ctx.get("news_titles"))
    news_changed = mock or (nh!=prev.get("news_hash")) or not prev.get("news")   # berita belum baru -> ga re-summarize (pakai prev)
    if mock:
        data={"commentary":"BTC konsolidasi dekat mid 24h-range, funding tipis positif (pemegang long bayar) — momentum belum tegas. Dominance naik pelan, perhatikan rejection di high 24h.",
              "whale":"Top-trader condong LONG sementara ritel net SHORT — whale lawan ritel.","bias":"netral",
              "news":["ETF inflow melambat minggu ini","Funding rate kembali ke netral","Likuiditas order-book menebal di bid"]}
        err=None
    else:
        if not gemini_key():
            save({"off":True,"reason":"no_gemini_key","ts":int(time.time())}); print("no Gemini key -> ai_read.json off"); return
        txt,err=call_gemini(build_prompt(ctx, news_changed), max_tokens=600)
        data=extract_json(txt) if txt else None
    if not mock and (err or not data):
        # gagal: jangan timpa komentar bagus, tapi TETAP segarkan snapshot L/S (data baru)
        prev.setdefault("commentary",""); prev["last_error"]=err or "parse_fail"; prev["ts_try"]=int(time.time())
        prev["whale_ls"]=ctx.get("WHALE_long_short_top_trader"); prev["retail_ls"]=ctx.get("retail_long_short"); prev["taker"]=ctx.get("taker_buy_sell")
        save(prev); print("Gemini gagal:", err or "parse_fail"); return
    news=([x for x in data.get("news",[]) if x][:3]) if news_changed else (prev.get("news") or [])
    out={"off":False,"ts":int(time.time()),
         "commentary":data.get("commentary",""), "whale":data.get("whale",""), "bias":data.get("bias","netral"),
         "news":news, "news_hash":nh, "price":ctx.get("price"),
         "whale_ls":ctx.get("WHALE_long_short_top_trader"), "retail_ls":ctx.get("retail_long_short"), "taker":ctx.get("taker_buy_sell")}
    save(out); print("ai_read.json updated:", out["bias"], "| news", "BARU" if news_changed else "tetap", "|", out["commentary"][:50], "...")

def load():
    try: return json.load(open(OUT))
    except Exception: return {}
def save(d):
    tmp=OUT+".tmp"; json.dump(d,open(tmp,"w"),ensure_ascii=False,indent=1); os.replace(tmp,OUT)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--once",action="store_true"); ap.add_argument("--mock",action="store_true")
    ap.add_argument("--models",action="store_true",help="daftar model yg didukung key (diagnosa 429)")
    a=ap.parse_args()
    if a.models:
        from gemini import list_models, _models
        ms,err=list_models()
        print("fallback chain dipakai:", _models())
        print("model didukung key kamu:", ms if ms else ("GAGAL: "+str(err)))
    elif a.mock: generate(mock=True)
    elif a.once: generate(mock=False)
    else: ap.print_help()
