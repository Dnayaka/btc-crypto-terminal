#!/usr/bin/env python3
"""gemini.py — helper tipis call Google Gemini (REST, tanpa SDK).
Key disimpan di bot_secrets.json field "gemini" (sisi PRIVAT). Dipakai ai_gen.py (cron)
& config_admin.py (second-opinion). config_server.py PUBLIK TIDAK pakai ini (cuma baca file).

⚠️ Gemini = ANALISA/KOMENTAR saja. JANGAN sambungkan ke eksekusi trade (edge v20 tervalidasi)."""
import os, json, time, requests, urllib3
urllib3.disable_warnings()
HERE = "/home/dnayaka/Documents/dynamic_rsi/btc-terminal"
SEC  = os.path.join(HERE, "bot_secrets.json")
CFG  = os.path.join(HERE, "bot_config.json")
BASE = "https://generativelanguage.googleapis.com/v1beta/models"
URL  = BASE + "/{m}:generateContent"
VERIFY = os.environ.get("FETCH_VERIFY","0")=="1"
# kuota free tiap model BEDA -> coba berurutan. Bisa di-override via bot_config.json "gemini_models" / env GEMINI_MODELS.
DEFAULT_MODELS = ["gemini-2.5-flash-lite","gemini-2.0-flash-lite","gemini-flash-lite-latest","gemini-2.5-flash","gemini-2.0-flash"]

def gemini_key():
    """Ambil key Gemini dari bot_secrets.json (atau env GEMINI_KEY)."""
    try:
        s=json.load(open(SEC)); k=s.get("gemini","")
        if isinstance(k,str) and k: return k
    except Exception: pass
    return os.environ.get("GEMINI_KEY","")

def _models():
    env=os.environ.get("GEMINI_MODELS","")
    if env: return [m.strip() for m in env.split(",") if m.strip()]
    try:
        ms=json.load(open(CFG)).get("gemini_models")
        if isinstance(ms,list) and ms: return ms
    except Exception: pass
    return DEFAULT_MODELS

def _one(prompt, key, model, max_tokens, temp, timeout):
    try:
        r=requests.post(URL.format(m=model), params={"key":key},
            json={"contents":[{"parts":[{"text":prompt}]}],
                  "generationConfig":{"temperature":temp,"maxOutputTokens":max_tokens}},
            timeout=timeout, verify=VERIFY)
        if r.status_code==429: return None,"429"
        if r.status_code>=400: return None, f"http {r.status_code}: {r.text[:110]}"
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip(), None
    except Exception as e:
        return None, str(e)[:130]

def call_gemini(prompt, key=None, model=None, max_tokens=500, temp=0.4, timeout=25):
    """Coba beberapa model (fallback, kuota tiap model beda) + 1 retry backoff saat 429.
    Return (text, None) sukses; (None, error) gagal. Tak pernah raise."""
    key=key or gemini_key()
    if not key: return None,"no_key"
    models=[model] if model else _models()
    last="?"
    for m in models:
        txt,err=_one(prompt,key,m,max_tokens,temp,timeout)
        if txt: return txt,None
        last=err or "?"
        if err=="429":
            time.sleep(3)                       # backoff utk burst per-menit
            txt,err=_one(prompt,key,m,max_tokens,temp,timeout)
            if txt: return txt,None
            last=err or "429"
        # 429 atau model-not-found -> lanjut model berikutnya
    if last=="429":
        return None,"kuota Gemini habis (429) di semua model — tunggu reset harian, ganti model (cek `ai_gen.py --models`), atau aktifkan billing"
    return None,last

def list_models(key=None):
    """Daftar model yg didukung key ini (buat diagnosa 429/model)."""
    key=key or gemini_key()
    if not key: return None,"no_key"
    try:
        r=requests.get(BASE, params={"key":key}, timeout=15, verify=VERIFY)
        if r.status_code>=400: return None, f"http {r.status_code}: {r.text[:120]}"
        return [m["name"].split("/")[-1] for m in r.json().get("models",[])
                if "generateContent" in m.get("supportedGenerationMethods",[])], None
    except Exception as e:
        return None, str(e)[:130]

def extract_json(text):
    """Ambil objek JSON pertama dari teks (Gemini kadang bungkus ```json ... ```)."""
    if not text: return None
    t=text.strip()
    if t.startswith("```"):
        t=t.split("```",2)[1]
        if t.startswith("json"): t=t[4:]
    a=t.find("{"); b=t.rfind("}")
    if a<0 or b<0: return None
    try: return json.loads(t[a:b+1])
    except Exception: return None
