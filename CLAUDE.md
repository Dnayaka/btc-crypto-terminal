# CLAUDE.md — BITCOIN TERMINAL (dashboard) · panduan pengembangan

Panduan ngoprek/menambah fitur dashboard trading. **Dashboard = SATU file `config_server.py`** (server + 2 halaman HTML jadi satu). Aesthetic: Bloomberg-terminal (amber phosphor di hitam, IBM Plex Mono + Bricolage Grotesque).

---

## ⭐ ARAHAN TERBARU (28-Jun) — baca dulu

**1. Pengembangan HTML SELANJUTNYA → pakai `graphify`.** Per arahan user: semua pengembangan file HTML/terminal berikutnya gunakan **graphify**. ⚠️ Catatan implementor: konfirmasi dulu ke user apa persisnya `graphify` (library chart? design-tool? generator/pendekatan tertentu?) SEBELUM menerapkan ke file produksi — jangan menebak & merusak terminal yang sudah jalan. Direktif ini WAJIB dihormati di sesi HTML berikutnya.

**2. Lokasi folder PINDAH** → sekarang di `/home/dnayaka/Documents/dynamic_rsi/btc-terminal/` (sebelumnya `/home/dnayaka/btc-terminal`). Semua service & cron sudah diarahkan ke sini.

**3. Fitur baru ditambahkan:**
- **BTC Dominance + Total Mcap** di terminal publik (`config_server.py`): gauge dominance (bar visual) + 2 baris di Market Snapshot. Sumber = CoinGecko `/api/v3/global` (gratis, no-key, cache 120s) via endpoint `/api/global`.
- **Popup di admin** (`config_admin.py`): toast notification (slide-in, hijau/merah/amber) untuk hasil config-save/key-save/trade, + **modal konfirmasi** bergaya (ganti `confirm()` browser) untuk Buy/Sell — tampil LONG/SHORT + ukuran sebelum eksekusi.

**4. BOT jadi v20-ONLY + bug fixes (28-Jun).** Sleeve **funding & CVD DIHAPUS** (permintaan user) — bot kini murni v20 (alokasi 100%). `bot_v22.py` = runner cron (tetap dipakai run_bot.sh, nulis bot_v22_state.json), `bot_v20_funding.py` = library v20 (nama dipertahankan biar import/service tak putus). Bug yang diperbaiki:
  - 🔴 **Cooldown freeze (kritis):** dulu `step_v20` pakai indeks window-relatif `i` yg KONSTAN tiap cron (i=len-1) → `bse=i-last_exit_i` selalu 0 → re-entry searah terblok PERMANEN; funding/CVD debounce juga beku. Fix = indeks ABSOLUT `ai=open_time//BAR_MS`. Bukti: live-emu sliding-window FIXED=10 trade (==ground truth) vs OLD-bug=3 trade. Selftest tetap +3327%/557/64.3% (bot==eng, zero-drift).
  - 🟠 **Fetch error:** `fetch_klines` kini try/except → return None (dulu crash & bar ke-skip). `do_once` **backfill** semua bar belum-diproses (tahan cron terlewat / laptop sleep), bukan cuma bar terakhir.
  - 🟡 Stub eksekusi mati dihapus; eksekusi live = NET posisi awal→akhir (snapshot `prev_pos`).
  - ⚠️ Ganti index space → state DIRESET (`--reset`). Live `--once` terverifikasi jalan; admin `/api/status` tetap baca `sleeves.v20`.

**5. LIVE-EXEC di-hardening jadi REKONSILIASI (`sync_live`, ganti `execute_live`).** Sumber-kebenaran = posisi NYATA di exchange (bukan state paper). Tiap run: baca `read_position()` → dorong ke `desired` (delta). Memperbaiki 4 isu live: (1) **timing** — `desired = pos else pending` → entry dieksekusi di run yg SAMA dgn sinyal (≈ next-open, bukan telat 1 bar/15m); (2) **qty** — close pakai qty AKTUAL exchange (reduceOnly), flip/size-change benar; (3) **rekonsiliasi** — baca posisi nyata tiap run, self-heal; (4) **konfirmasi** — re-baca setelah order, WA alert kalau MISMATCH. Toleransi ½-lot (0.0005). Diuji 14/14 via mock-exchange TANPA key (`scratchpad/stress_live.py`).
  - **Fetch 500→1000 bar**: EMA200 konvergen penuh (div vs full-history 0.05%→0.0003%) → sinyal live == backtest dijamin.
  - ⚠️ **Manual button vs bot:** karena bot kini AUTHORITATIVE atas posisi v20, trade manual (admin Buy/Sell) di simbol yg sama akan **di-reconcile (ditutup)** di run bot berikutnya. Mau pegang posisi manual → set `sleeves.v20=false` dulu.
  - ⚠️ **Exit slippage (sisa, bukan bug):** SL/TP/trailing dideteksi saat close-bar lalu market-close (granularitas 1 bar). Backtest asumsi fill intrabar di level SL/TP. Trailing chandelier update tiap bar → tak bisa jadi 1 resting-order. Diterima sbg karakteristik bot-polling.
  - **Manual `place_market` di-gate `live`** + leverage hard-cap 1x (footgun ditutup sesi ini).

**6. DUA SWITCH (28-Jun): PAPER/LIVE + TESTNET/MAINNET.** Mode = kombinasi 2 toggle di admin:
  - `live=false` → **PAPER** (nol order, dimana pun net).
  - `live=true & net=testnet` → order REAL di **Binance testnet** (uang PALSU, aman validasi eksekusi). ccxt `set_sandbox_mode(True)`.
  - `live=true & net=mainnet` → **UANG ASLI**. UI: badge merah, confirm dialog "UANG ASLI".
  - **Key per-net**: `bot_secrets.json` = `{"mainnet":{key,secret},"testnet":{key,secret}}` (backward-compat flat=mainnet). Admin simpan/baca key sesuai net terpilih; testnet & mainnet key BEDA (daftar di testnet.binancefuture.com). Sinyal/data SELALU dari mainnet (real market); cuma EKSEKUSI yg dirute ke net.
  - Default aman = `net=testnet`. Config field `net` di bot_config.json. `load_keys(net)`/`_exchange(net)` di bot + admin.
  - **eng.py time-stop bug laten DI-FIX** (btc-terminal copy saja; `last_exit_dir` dulu selalu -1 krn `pos=0` sebelum cek sign). Dormant di v20 (max_hold=0) tapi sudah benar. Copy riset `Documents/claude/eng.py` TAK disentuh.
  - Tes: live-recon+net-routing 16/16, bot 13/13, eng max_hold=50 jalan, selftest tetap +3327/557/64.3. Harness: scratchpad sesi b3964f21.

**7. AI tambahan: GEMINI (28-Jun) — komentar/analisa, BUKAN keputusan trade.** ⚠️ Sengaja TERPISAH dari eksekusi bot (edge v20 tervalidasi; LLM di jalur trade = risiko). 3 peran:
  - **Komentar pasar + ringkas berita** di terminal PUBLIK (panel "AI Read · Gemini" + bias bullish/bearish/netral).
  - **Second opinion** sinyal/posisi bot di ADMIN (tombol → komentar netral live).
  - **Key Gemini di sisi PRIVAT** (`bot_secrets.json` field `gemini`). Publik NOL key (grep gemini di config_server = 0).
  - **Alur**: `gemini.py` (helper REST, no SDK) → `ai_gen.py` (cron `5,35 * * * *`, ambil data dari endpoint publik sendiri, panggil `gemini-2.0-flash`, tulis `ai_read.json`) → config_server `/api/ai` cuma BACA file (no key, quota aman walau di-share). Admin `/api/secondopinion` panggil Gemini live.
  - **Key GRATIS** dari Google AI Studio (aistudio.google.com). Tanpa key → panel "AI off" rapi. `ai_read.json`/`ai_gen.log` gitignored.

**8. CIRCUIT-BREAKER + verifikasi TESTNET (28-Jun, pra-live).**
  - **Circuit-breaker** (`check_breaker` di bot_v20_funding, dipanggil do_once SEBELUM eksekusi): halt kalau **DD dari puncak ≥ `max_dd_pct`** (default 15%) ATAU **loss beruntun ≥ `max_loss_streak`** (default 6). Trip → flat posisi (live masih on) → `set_config(live=false, halted=true)` → WA "🛑 CIRCUIT BREAKER". Cuma trip saat live=true (lindungi uang asli). Config `bot_config.json "breaker"`. `loss_streak` ditrack di step_v20 tiap exit. Reset: `bot_v22.py --resume` (live tetap OFF, nyalakan manual). Diuji 15/15 (`scratchpad/stress_breaker.py`).
  - **`verify_testnet.py`**: validasi mekanik eksekusi di Binance testnet (uang palsu). AMAN: refuse kalau net≠testnet (3 gate teruji), selalu flat di akhir. Cek: auth, open long qty-benar, close exact-qty, open short, FLIP, posisi-akhir-flat.
  - **`TESTNET_CHECKLIST.md`**: checklist FASE 0-5 (daftar key testnet → verify → forward run → uji breaker → go/no-go → cutover mainnet kecil). ⚠️ **Status live: BELUM divalidasi eksekusi nyata** — code matang & lulus mock (44 tes), tapi WAJIB run testnet dulu sebelum mainnet.
  - **429 quota = per-MODEL, bukan bug.** `call_gemini` punya **fallback chain** (model `lite` dulu = kuota free lebih besar) + retry backoff 3s saat 429. Default: `gemini-2.5-flash-lite → 2.0-flash-lite → flash-lite-latest → 2.5-flash → 2.0-flash`. Override via `bot_config.json "gemini_models"` / env `GEMINI_MODELS`. Diagnosa model yg didukung key: `python3 ai_gen.py --models`. (gemini-1.5-* sudah deprecated di env 2026.) ⚠️ **config_admin = service** → restart `systemctl --user restart bot-admin` kalau ubah `gemini.py` (ai_gen.py fresh tiap run, tak perlu). Cron ai_gen diturunkan ke **hourly** (`5 * * * *`) biar hemat kuota harian.

---

## 1. DI MANA FILE-NYA (peta)
Semua di **`/home/dnayaka/Documents/dynamic_rsi/btc-terminal/`** (bukan di folder terminal/ ini — ini cuma docs):

**⚠️ DUA SERVER terpisah (public vs private) — keamanan:**

| File | Fungsi |
|---|---|
| **`config_server.py`** | 🌐 **PUBLIC TERMINAL** :8788 (bind 0.0.0.0) — **READ-ONLY market data** (chart/liquidity/stats/news, multi-asset BTC/ETH/SOL). **TANPA key, TANPA trading.** Aman dishare/deploy publik. |
| **`config_admin.py`** | 🔒 **PRIVATE ADMIN** :8789 (**bind 127.0.0.1 ONLY**) — key + config (live/size/lev) + manual execute + position. **JANGAN expose ke publik.** |
| `bot_config.json` | config (live/size/leverage). Ditulis HANYA oleh admin. |
| `bot_secrets.json` | API key (chmod 600). Diisi HANYA via admin. **JANGAN ada di server publik.** |
| `bot_v22_state.json` | posisi/equity (dari bot). Dibaca admin. |
| `bot_v22.py` / `bot_v20_funding.py` | BOT (cron 15m). `execute_live()` & `load_keys()`. |
| `notify_wa.py` | kirim WhatsApp. |

**Aturan kunci:** data privat (key/posisi/trade) **HANYA** di `config_admin.py` (localhost). `config_server.py` cuma proxy data pasar publik (Binance/news) → boleh dibuka ke internet. Endpoint `/api/secrets`, `/api/trade`, POST `/api/config` **TIDAK ADA** di server publik.

**Services:**
```bash
systemctl --user restart bot-config   # PUBLIC :8788
systemctl --user restart bot-admin    # PRIVATE :8789
journalctl --user -u bot-config -f
```
Akses: PUBLIC `http://localhost:8788` (boleh share/deploy) · PRIVATE `http://localhost:8789` (laptop ini saja, jangan ufw-allow ke LAN kecuali sadar risiko).

---

## 2. ARSITEKTUR config_server.py (urutan dalam file)
```
1. helper        : load()/save() config, load_keys(), place_market(side)  [eksekusi ccxt]
2. CSS           : string r"""...""" — semua style (CSS variables di :root)
3. HEAD          : <head> + <style>+CSS  (dipakai dua halaman, biar DRY)
4. MAIN          : HTML halaman utama (/)  = HEAD + body + <script>
5. TRADE         : HTML halaman /trade     = HEAD + body + <script>
6. class H       : router. do_GET (halaman + /api/* GET), do_POST (/api/* aksi)
```
**Pola:** backend = proxy data (Binance/alternative.me/CoinTelegraph) → JSON. Frontend = `fetch('/api/...')` + render (lightweight-charts + vanilla JS, fungsi `loadX()` + `setInterval`).

---

## 3. ENDPOINT yang ada
| GET | Sumber | Isi |
|---|---|---|
| `/` , `/trade` | — | halaman HTML |
| `/api/klines?tf=15m` | Binance fapi | 500 candle OHLC + **volume** |
| `/api/metrics` | Binance + alternative.me | funding, mark, fear&greed |
| `/api/liquidity` | Binance fapi | order-book imbalance, bid/ask wall, OI, retail L/S, top L/S |
| `/api/status` | bot_v22_state.json + WA daemon | posisi v20, equity, WA connected |
| `/api/config` `/api/secrets` | file lokal | config & status key |
| `/api/news` | CoinTelegraph RSS | berita BTC |
| POST `/api/config` `/api/secrets` `/api/trade` | — | simpan config / key / market order |

---

## 4. CARA NAMBAH FITUR

### a) Nambah PANEL baru
1. Di `MAIN`, tambah `<section class="panel rv d5"><div class=panel-h><span class=t><span class=sq></span>Judul</span></div><div id=isi></div></section>`
2. Di `<script>`, bikin `function loadX(){fetch('/api/x').then(r=>r.json()).then(d=>{ $('isi').innerHTML=... })}` + panggil di init + `setInterval(loadX,30000)`
3. (kalau perlu data baru) tambah endpoint di `do_GET` (lihat pola `/api/metrics`).

### b) Nambah INDIKATOR chart (mis. EMA, MACD)
Hitung di JS dari `klines` (lihat fungsi `RSI()` sebagai contoh). Lalu:
- overlay di chart utama: `chart.addLineSeries({color})` + `.setData(...)`
- pane terpisah (kayak RSI): bikin `LightweightCharts.createChart($('paneBaru'))`, sync timescale dgn `subscribeVisibleLogicalRangeChange`.

### c) Nambah ASET / **ANALISA SAHAM** ⭐
Struktur chart/indikator/news **sudah asset-agnostic** — tinggal ganti SUMBER DATA. Pola "adapter":

1. **Symbol switcher**: tambah dropdown/segment di header, simpan `curSym`, kirim ke `/api/klines?sym=...`.
2. **Adapter di backend** — routing per kelas aset di `/api/klines`:
   ```python
   sym = parse_qs(p.query).get("sym",["BTCUSDT"])[0]
   if sym.endswith("USDT"):           # crypto -> Binance (sudah ada)
       ... fapi/klines ...
   else:                              # SAHAM -> sumber saham
       ... panggil adapter_stock(sym, tf) ...
   ```
3. **Sumber data SAHAM** (stocks gak ada di Binance) — pilih satu, **butuh API key gratis**:
   | Sumber | Free? | Catatan |
   |---|---|---|
   | **Alpha Vantage** | ✅ (key gratis) | `TIME_SERIES_INTRADAY`/`DAILY`, limit 25 req/hari free |
   | **Finnhub** | ✅ (key gratis) | candle saham + news, 60 req/min |
   | **Twelve Data** | ✅ (key gratis) | `/time_series`, mudah, 800 req/hari |
   | Yahoo / Stooq | ⚠️ | sering ke-blokir di env ini (sudah dites gagal) — hindari |
   Adapter tinggal ubah respons ke format `{time,open,high,low,close,volume}` (sama kayak klines crypto) → chart langsung jalan.
4. **Metrics/liquidity** khusus crypto (funding/OI/orderbook) — buat saham, ganti panel itu dgn metrik saham (P/E, volume, market cap, dll dari sumber yg sama) atau sembunyikan kalau `sym` saham.
5. **News**: ganti RSS ke feed saham (mis. Finnhub `/news?category=general` atau RSS market).

> Intinya: **1 adapter data per kelas aset → output OHLCV seragam**. UI (chart/RSI/volume/line) nggak perlu diubah.

### d) Nambah endpoint
Tambah `if path=="/api/...":` di `do_GET` (atau `do_POST`). Bungkus `try/except`, balikin `self._s(200,"application/json",json.dumps(...))`.

---

## 5. SISTEM AESTHETIC (cara ubah look)
Semua warna/font lewat **CSS variables di `:root`** (atas blok CSS):
```
--bg --panel --ink --dim --amber --amber2 --up --down --line
--mono:'IBM Plex Mono'   --disp:'Bricolage Grotesque'
```
- **Lebih Bloomberg-klasik**: ubah `--amber` ke oranye Bloomberg `#ff8c1a`, perkecil font data jadi 11-12px, rapatkan padding panel, tambah lebih banyak baris-tabel angka (Bloomberg = padat data). Ganti `--bg` ke `#000`.
- **Ganti tema**: cukup ubah variabel — semua komponen ikut.
- Layer atmosfer (`.bg .scan .grain .vig`) = depth; matikan dgn `display:none` kalau mau flat.
- Ganti font: ubah `<link>` Google Fonts + `--mono`/`--disp`. (Hindari Inter/Roboto/Space Grotesk — bikin generic.)

---

## 6. ATURAN AMAN (penting, ini nyentuh uang asli)
- `place_market()` & auto-exec baca `bot_secrets.json` + `bot_config.json`. **Default `live:false`** (paper). Test pakai size kecil dulu.
- Min order Binance BTCUSDT ~**$100 notional** — sudah dicek di `place_market` & UI.
- Eksekusi otomatis bot = **cuma sleeve v20** (long/short, 1 posisi/akun). funding/CVD = sinyal WA.
- Jangan commit `bot_secrets.json` ke git. Sudah chmod 600.

---

## 7. WORKFLOW NGOPREK (langkah)
```bash
cd /home/dnayaka/Documents/dynamic_rsi/btc-terminal
nano config_server.py                 # edit HTML/CSS/endpoint
python3 -c "import ast;ast.parse(open('config_server.py').read())"   # cek syntax
systemctl --user restart bot-config   # apply
curl -s localhost:8788/api/metrics    # test endpoint
# buka browser localhost:8788, refresh
```
Screenshot cepat buat cek tampilan:
```bash
chromium --headless=new --no-sandbox --window-size=1200,2200 --virtual-time-budget=9000 \
  --screenshot=/tmp/dash.png http://localhost:8788
```

---

## 8. IDE PENGEMBANGAN (backlog)
- [ ] Symbol switcher BTC/ETH/SOL (crypto, gampang — semua di Binance fapi)
- [ ] Tab "Stocks" (adapter Finnhub/Twelve Data + key)
- [ ] EMA/MACD/Bollinger overlay di chart
- [ ] Liquidation feed (butuh Coinglass/paid — atau approximate)
- [ ] Equity curve bot (dari paper_trades / state history)
- [ ] Mode lebih padat (Bloomberg classic): tabel multi-aset, watchlist
- [ ] Dark/amber theme toggle (cukup swap CSS variables)

> Pegangan: **backend = adapter data → JSON seragam. Frontend = panel + loadX() + interval. Aesthetic = CSS variables.** Tiga lapis itu bikin nambah aset/saham/indikator jadi gampang.

---

## 9. CHART STRATEGI v20 (TradingView-style) — ATURAN PENTING (29-Jun)
- **Strategi v20 di-hitung HANYA di timeframe 15m** (engine `eng.py`+`bot_v20_funding.pbsig`, tervalidasi 557 trade WR64.27/+3327%). Sumber: `btc15m.py` → `btc_v20.json` (bars 3000=31hr, markers + `trades[]` {et,xt,entry,tp,sl,ret,win} window ~24000 bar/250hr), endpoint `/api/btc_v20`. Cron 5m incremental gap-fetch (`btc15m.py`, cuma tarik bar baru cache→now via cors.sh, ga boros).
- **Sinyal buy/sell tetap dari 15m, tapi DITAMPILKAN di TF apapun dgn SNAP ke candle TF** (`snap(t,tf)=floor(t/tfSec)*tfSec`, TFS 15m/1h/4h/1d). Contoh: 15m buy 07:00 + TP 08:15 → di 1h tampil buy candle 07:00, TP candle 08:00. Marker + box di-snap di `applyV20()`.
- **Visual = TradingView "position box"**: custom primitive lightweight-charts `TradeBoxes` (canvas) gambar zona HIJAU (entry→TP) + MERAH (entry→SL) spanning entry→exit + garis entry/TP/SL + arrow LONG/SHORT + label return% per trade. Title = WR/ret/nL-nS.
- **HANYA BTC.** ETH/SOL **TIDAK** dapat strategi/marker/box ("jangan dulu") — `loadChart` non-BTC: `candleS.setMarkers([]);boxes.set([])`. TIAP ticker+TF punya data sendiri (BTC pakai btc_v20 utk 15m + klines TF lain; ETH/SOL klines polos).
- Chart live-sync: `tickChart` 3s update bar-terakhir via `.update()` (no redraw), **zoom kepertahanin** (save/restore `getVisibleRange`), `chartReady` guard anti-race, `setView` deferred 60ms (fix container-timing). `refreshV20` 60s re-apply marker/box.
- Nambah strategi ticker lain nanti: bikin `{ticker}15m.py` → `{ticker}_v20.json` + endpoint, mirror pola BTC. JANGAN apply v20 BTC ke ticker lain.

---

## 10. STATISTICAL TRIPWIRE (2-Jul) — proteksi tambahan di atas circuit-breaker

**Beda dari circuit-breaker yang sudah ada** (§ arahan 28-Jun poin 8, `check_breaker` = titik-ekstrem tunggal DD≥15%/loss-streak≥6): tripwire ini bereaksi ke **bentuk distribusi rolling**, jauh lebih sensitif — dirancang nangkep anomali lebih dini, sebelum kondisi separah breaker.

- **4 metrik + floor/ceiling** (`TRIPWIRE` dict di `bot_v20_funding.py`), diturunkan dari replay `eng.run()` (558 trade futures 2019-2025, kode identik production) DAN cross-check TradingView list-of-trades asli (733 trade 2017-2026, beberapa basis position-sizing dicoba: compounding penuh, fixed-notional, 10%-of-equity — semua diverifikasi konsisten arah meski beda skala persis):
  - Rolling-41 WR (semua trade) floor **46.3%** (historical min sendiri ≈48.8%)
  - Rolling-41 return compounded floor **−4.7%** (TV-data cross-check ≈−2.9% s/d −8.8% tergantung basis sizing — −4.7% ada di tengah rentang itu, TIDAK reproduksi exact dari satu model tunggal, diterima sbg reasonable)
  - Rolling-30 WR SHORT-only floor **46.7%** (exact match replay python)
  - DD-dari-puncak (closed equity, reuse `check_breaker`'s dd) ceiling **11.1%** (near-exact match, replay 10.97%)
- **2-tier**: 1 metrik breach → `size_mult=0.5` (potong size order berikutnya 50%, via `sync_live`'s `size_usd *= cfg['tripwire_size_mult']`); **≥2 metrik breach BARENGAN** → pause total (flatten+`live=false`+`halted=true`, sama efek dgn circuit-breaker, WA alert). Validasi replay historis: **14× tier1** (semua dari WR-30-short nyentuh floor-nya, klaster Feb–Jun 2024), **0× tier2** (belum pernah 2 metrik breach bareng dlm 6 tahun — koheren karena tiap floor emang titik-ekstrem masing2 metrik).
- **State**: `new_sleeve()['hist']` = list `{dir,net}` per trade closed, cap 100 entri (append di `step_v20()` LONG & SHORT exit branch). Butuh histori cukup dulu (≥41 utk wr41/ret41, ≥30 short utk wr30_short) sebelum metrik terkait dievaluasi — state lama (pra-fitur ini) mulai kosong `hist=[]`, tripwire baru aktif prospektif seiring trade baru terkumpul, TIDAK retroaktif.
- **Config**: `bot_config.json` `"tripwire":{"enabled":true}` (toggle on/off, thresholds sendiri HARDCODE di kode — riset-derived, bukan knob operasional casual) + `"tripwire_size_mult"` (1.0 normal, 0.5 saat tier1, auto-reset pas metrik pulih). `bot_v22.py --resume` reset breaker DAN tripwire sekaligus.
- **Admin UI**: `/api/status` (`config_admin.py`) expose `breaker`+`tripwire` (exclude raw `hist` dari payload, cuma dipakai server-side). Panel Position tampilkan banner merah (halted/tier2) atau kuning (tier1) kalau ada breach.
- **Fungsi**: `check_tripwire(st, cfg, breaker_dd)` di `bot_v20_funding.py`, dipanggil `bot_v22.py:do_once()` SETELAH `check_breaker` (breaker dulu, baru tripwire — breaker lebih ekstrem/prioritas). Derivasi angka: scratchpad sesi `tripwire_calc.py` (python replay) + `tv_tripwire.py` (parse TV CSV export, termasuk reconcile 10%-equity-sizing model yg cocok persis `Cumulative PnL%` TV — 38.593 vs 38.59 reported).
