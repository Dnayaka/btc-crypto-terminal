# Graph Report - .  (2026-07-02)

## Corpus Check
- 134 files · ~478,049 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 747 nodes · 1207 edges · 86 communities (70 shown, 16 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 34 edges (avg confidence: 0.83)
- Token cost: 411,767 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Private Admin Server|Private Admin Server]]
- [[_COMMUNITY_Live Bot Execution Engine|Live Bot Execution Engine]]
- [[_COMMUNITY_Project Documentation|Project Documentation]]
- [[_COMMUNITY_AI Commentary Generator|AI Commentary Generator]]
- [[_COMMUNITY_Main Dashboard Screenshot|Main Dashboard Screenshot]]
- [[_COMMUNITY_V20 Strategy Chart Data|V20 Strategy Chart Data]]
- [[_COMMUNITY_Economic Calendar Fetcher|Economic Calendar Fetcher]]
- [[_COMMUNITY_Scalping Strategy Research|Scalping Strategy Research]]
- [[_COMMUNITY_Entry Signal Research|Entry Signal Research]]
- [[_COMMUNITY_DCA Strategy Research|DCA Strategy Research]]
- [[_COMMUNITY_Strategy Engine Utilities|Strategy Engine Utilities]]
- [[_COMMUNITY_Multi-Symbol V20 Generator|Multi-Symbol V20 Generator]]
- [[_COMMUNITY_External Feature Research|External Feature Research]]
- [[_COMMUNITY_Money Flow Indicators|Money Flow Indicators]]
- [[_COMMUNITY_Portfolio Backtest Library|Portfolio Backtest Library]]
- [[_COMMUNITY_WhatsApp Daemon Config|WhatsApp Daemon Config]]
- [[_COMMUNITY_Macro Event Filter Research|Macro Event Filter Research]]
- [[_COMMUNITY_IDX Broker Summary Scraper|IDX Broker Summary Scraper]]
- [[_COMMUNITY_Binance DNS Proxy|Binance DNS Proxy]]
- [[_COMMUNITY_Entry Verification Research|Entry Verification Research]]
- [[_COMMUNITY_V23 Re-entry Research|V23 Re-entry Research]]
- [[_COMMUNITY_Journal PnL Card Screenshot|Journal PnL Card Screenshot]]
- [[_COMMUNITY_IDX ARA Limit Analysis|IDX ARA Limit Analysis]]
- [[_COMMUNITY_IDX Strategy Equity Chart|IDX Strategy Equity Chart]]
- [[_COMMUNITY_Stock Data Fetcher|Stock Data Fetcher]]
- [[_COMMUNITY_IDX Market Data Fetcher|IDX Market Data Fetcher]]
- [[_COMMUNITY_Deploy Fetch Research|Deploy Fetch Research]]
- [[_COMMUNITY_WhatsApp Baileys Daemon|WhatsApp Baileys Daemon]]
- [[_COMMUNITY_Fed DCA Research|Fed DCA Research]]
- [[_COMMUNITY_Partial Exit Research|Partial Exit Research]]
- [[_COMMUNITY_Regime Filter Verification|Regime Filter Verification]]
- [[_COMMUNITY_Journal Demo Page Logic|Journal Demo Page Logic]]
- [[_COMMUNITY_Installer Script|Installer Script]]
- [[_COMMUNITY_Order Book Recorder|Order Book Recorder]]
- [[_COMMUNITY_Paper Order Book Simulator|Paper Order Book Simulator]]
- [[_COMMUNITY_Entry Filter Research|Entry Filter Research]]
- [[_COMMUNITY_Multi-Timeframe Research|Multi-Timeframe Research]]
- [[_COMMUNITY_IHSG Technical Analysis|IHSG Technical Analysis]]
- [[_COMMUNITY_Regime Filter Variant 4|Regime Filter Variant 4]]
- [[_COMMUNITY_Mean-Reversion Validation|Mean-Reversion Validation]]
- [[_COMMUNITY_Mainnet Order Book Verification|Mainnet Order Book Verification]]
- [[_COMMUNITY_Static Demo Generator|Static Demo Generator]]
- [[_COMMUNITY_Real Liquidation Data Fetcher|Real Liquidation Data Fetcher]]
- [[_COMMUNITY_IDX Foreign Flow History|IDX Foreign Flow History]]
- [[_COMMUNITY_Regime Filter Base Research|Regime Filter Base Research]]
- [[_COMMUNITY_Sleeve Gate Research|Sleeve Gate Research]]
- [[_COMMUNITY_Chart TradeBoxes Primitive|Chart TradeBoxes Primitive]]
- [[_COMMUNITY_Stock Signal Cron Script|Stock Signal Cron Script]]
- [[_COMMUNITY_Low-Cap Stock Fetcher|Low-Cap Stock Fetcher]]
- [[_COMMUNITY_V23 Advanced Training|V23 Advanced Training]]
- [[_COMMUNITY_V23 Breakeven Training|V23 Breakeven Training]]
- [[_COMMUNITY_V23 FOMC Training|V23 FOMC Training]]
- [[_COMMUNITY_Testnet Execution Verification|Testnet Execution Verification]]
- [[_COMMUNITY_WhatsApp Heartbeat Script|WhatsApp Heartbeat Script]]
- [[_COMMUNITY_Bot Cron Runner|Bot Cron Runner]]
- [[_COMMUNITY_Testnet Checklist Doc|Testnet Checklist Doc]]
- [[_COMMUNITY_Static Preview Page|Static Preview Page]]

## God Nodes (most connected - your core abstractions)
1. `run()` - 25 edges
2. `rsi()` - 22 edges
3. `atr()` - 22 edges
4. `ema()` - 21 edges
5. `signals()` - 21 edges
6. `pbsig()` - 18 edges
7. `do_once()` - 16 edges
8. `build_v20_context()` - 13 edges
9. `H` - 13 edges
10. `gemini_key()` - 13 edges

## Surprising Connections (you probably didn't know these)
- `RSI() JS function` --conceptually_related_to--> `v20 strategy (RSI-momentum breakout + pullback + regime-TP)`  [INFERRED]
  docs/index.html → CLAUDE.md
- `build_v20_context()` --calls--> `atr()`  [EXTRACTED]
  bot_v20_funding.py → eng.py
- `build_v20_context()` --calls--> `ema()`  [EXTRACTED]
  bot_v20_funding.py → eng.py
- `build_v20_context()` --calls--> `rsi()`  [EXTRACTED]
  bot_v20_funding.py → eng.py
- `build_v20_context()` --calls--> `signals()`  [EXTRACTED]
  bot_v20_funding.py → eng.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Testnet-before-mainnet validation flow** — claude_verify_testnet, testnet_checklist, claude_check_breaker, claude_two_switch_mode [EXTRACTED 0.85]
- **Public/private server security separation** — claude_md_config_server_py, claude_md_config_admin_py, claude_md_bot_secrets_json, claude_md_bot_config_json [EXTRACTED 0.95]
- **Gemini AI commentary pipeline (key-isolated)** — claude_md_gemini_py, claude_md_ai_gen_py, claude_md_ai_read_json, claude_md_config_server_py [EXTRACTED 0.95]
- **Layered risk control (breaker + tripwire)** — claude_md_check_breaker, claude_md_check_tripwire, claude_md_circuit_breaker, claude_md_statistical_tripwire, claude_md_do_once [EXTRACTED 0.95]

## Communities (86 total, 16 thin omitted)

### Community 0 - "Private Admin Server"
Cohesion: 0.05
Nodes (62): BaseHTTPRequestHandler, H, load(), load_fedlive(), load_keys(), place_market(), Terima URL YouTube (watch/live/youtu.be/embed) ATAU raw video-id (11 char) -> vi, Per-net: {"mainnet":{key,secret},"testnet":{key,secret}}. Backward-compat flat = (+54 more)

### Community 1 - "Live Bot Execution Engine"
Cohesion: 0.07
Nodes (47): acquire_lock(), alert(), bget(), build_v20_context(), check_breaker(), check_tripwire(), do_once(), _exchange() (+39 more)

### Community 2 - "Project Documentation"
Cohesion: 0.05
Nodes (48): CLAUDE.md (btc-terminal dev guide), Bloomberg-terminal CSS-variable theming system, ai_gen.py (AI commentary cron), ai_read.json, Asset adapter pattern (1 adapter per asset class -> uniform OHLCV), bot_config.json, bot_secrets.json (chmod 600), bot_v20_funding.py (v20 library) (+40 more)

### Community 4 - "AI Commentary Generator"
Cohesion: 0.11
Nodes (32): build_context(), build_prompt(), generate(), _get(), load(), _news_hash(), Rangkai snapshot pasar dari endpoint publik SENDIRI (sudah agregasi Binance/news, save() (+24 more)

### Community 5 - "Main Dashboard Screenshot"
Cohesion: 0.08
Nodes (36): config_server.py (btc-terminal public server, contains journal string references), New trade entry form (ENTRI BARU: symbol, date, long/short, modal, entry/exit, SL, leverage, PnL, notes, screenshot upload), Trade history list (RIWAYAT - privat, per-trade cards with pamer/edit/hapus actions), PnL Calendar heatmap (KALENDER PNL, monthly grid, profit/loss/no-trade color coding), Trading Journal feature (dnayaka's private per-account trade log), Win rate / total PnL summary tracking (Total PnL, Bulan ini, Win rate %, Trade tercatat), BTC / ETH / SOL asset selector tabs (Perpetual, Binance Futures), Bloomberg-terminal visual style: amber-on-black phosphor palette, monospace data typography, dense panel layout (+28 more)

### Community 6 - "V20 Strategy Chart Data"
Cohesion: 0.15
Nodes (17): build_v20_context_multi(), pbsig(), Pullback-continuation additive (identik eng test harness / pine v19-v20)., Generalized build_v20_context, param per-symbol (MULTI_PARAMS). BTC path via, build(), update_csv(), v20_trades(), atr() (+9 more)

### Community 7 - "Economic Calendar Fetcher"
Cohesion: 0.18
Nodes (18): bls_actual(), _econ_compute(), fetch(), fetch_adp_actual(), fetch_bls(), fetch_dbnomics(), _flist(), load_bls() (+10 more)

### Community 8 - "Scalping Strategy Research"
Cohesion: 0.15
Nodes (14): backtest(), ema(), Fade: RSI oversold -> long (harap mantul 200$); overbought -> short., Harga tembus band bawah -> long (revert ke mean); band atas -> short., Micro-momentum: tembus high N-bar -> long; low -> short., ⭐ Mean-rev SEARAH tren (temuan validasi 30-Jun, 4/4 walk-forward GROSS):     LON, rma(), rsi() (+6 more)

### Community 9 - "Entry Signal Research"
Cohesion: 0.16
Nodes (15): build_mask(), build_mask_conf(), build_mask_filt(), down_streak(), ev(), eval_cf(), evc(), evf() (+7 more)

### Community 10 - "DCA Strategy Research"
Cohesion: 0.24
Nodes (10): indicators(), signals(), a_i(), dca_pct=None -> baseline (faithful eng). else add 1 unit di X% adverse., run_dca(), run_dca_slice(), metrics(), oos() (+2 more)

### Community 11 - "Strategy Engine Utilities"
Cohesion: 0.26
Nodes (11): atr(), entry_exit(), indicators(), _metrics(), Pool semua trade lintas simbol (equal-weight, 1 posisi/sinyal). Edge AGREGAT uni, rma(), rollmax(), rsi() (+3 more)

### Community 12 - "Multi-Symbol V20 Generator"
Cohesion: 0.23
Nodes (8): run(), build(), update_csv(), v20_trades(), run_thr(), base_kw(), m(), run_block()

### Community 13 - "External Feature Research"
Cohesion: 0.21
Nodes (11): broadcast(), daily_feats(), _dir_mask(), oostest(), peryear(), Mask arah: long diizinkan saat roc<0 (atau >0 kalau long_when_neg=False), short, Broadcast fitur harian (indexed by use_date) ke tiap bar 15m via merge_asof (for, mask_long/short: bool array (True=izinkan entry). tp_mult/sl_mult: array pengali (+3 more)

### Community 14 - "Money Flow Indicators"
Cohesion: 0.27
Nodes (11): buysell_pct(), _clean(), cmf(), mfi(), obv_trend(), % volume di hari NAIK (proxy tekanan beli) selama n hari. >55 akumulasi, <45 dis, NaN/inf -> None (JSON-safe), selain itu round., INFERENSI SM-vs-retail dari pola price+volume (BUKAN broksum kode-broker asli). (+3 more)

### Community 15 - "Portfolio Backtest Library"
Cohesion: 0.35
Nodes (9): all_trades(), evaluate(), load_data(), per_year(), perturb(), portfolio(), Fraksi tetangga param yg tetap (mean>0 & WR>=60). >=0.8 = plateau., Ringkasan komparabel: full / holdout(2024-26) / portfolio / per-year-min / pertu (+1 more)

### Community 16 - "WhatsApp Daemon Config"
Cohesion: 0.20
Nodes (9): dependencies, express, pino, qrcode-terminal, @whiskeysockets/baileys, description, main, name (+1 more)

### Community 17 - "Macro Event Filter Research"
Cohesion: 0.28
Nodes (6): macro_mask(), oostest(), peryear(), True di bar yg dlm jendela [-hours_before, +hours_after] jam dari SALAH SATU eve, mask_block: True=BLOK entry baru di bar ini. sl_mult: array pengali SLa (None=1x, run_variant()

### Community 18 - "IDX Broker Summary Scraper"
Cohesion: 0.36
Nodes (8): fetch_one(), load_cookie(), main(), parse(), curl_cffi impersonate Chrome (TLS = browser asli) + cookie cf_clearance dari bro, IDX broksum -> top broker net beli & net jual. Fleksibel thd bentuk respons., session(), watchlist_syms()

### Community 19 - "Binance DNS Proxy"
Cohesion: 0.29
Nodes (5): doh(), handle(), pipe(), Resolve A-record via Cloudflare DoH (HTTPS) -> IP asli (kebal DNS-hijack ISP). C, Relay src->dst. Kalau fragment_first: split kiriman PERTAMA jadi byte-1 + sisany

### Community 20 - "Entry Verification Research"
Cohesion: 0.36
Nodes (5): entry_mask(), perturb(), Apply mask as extra_long on base mr_rsi cf with base RSI gate disabled., report(), run_trades()

### Community 21 - "V23 Re-entry Research"
Cohesion: 0.48
Nodes (5): metrics(), oos(), reidx = 0 entry awal, 1.. = re-entry ke-n., run_qtp(), size_of()

### Community 22 - "Journal PnL Card Screenshot"
Cohesion: 0.52
Nodes (7): Trading Journal - PnL Card & Calendar screenshot, CRYPTO nav button in header (navigates away from journal to crypto/market view), Dark background with amber/orange accent visual theme (consistent with Bloomberg-terminal aesthetic used across btc-terminal), Entri Baru (New Entry) trade logging form: symbol, date/time, LONG/SHORT toggle, modal/entry/exit/SL fields, leverage, PnL, notes textarea, screenshot attach, save button, Kalender PnL (monthly calendar heatmap, Juli 2026, per-day PnL cells color-coded green/red), Total PnL summary card (shows +$378.71 total, month-to-date, win rate 67%, 9 trades logged), Trading Journal page (personal PnL tracking UI, separate from main BTC terminal dashboard)

### Community 23 - "IDX ARA Limit Analysis"
Cohesion: 0.38
Nodes (5): ara_limit(), backtest_setup(), features(), Batas Auto-Reject Atas (approx simetris post-2021)., Fitur low-cap utk saringan: volume surge, range/consolidation, prior-ARA, posisi

### Community 24 - "IDX Strategy Equity Chart"
Cohesion: 0.52
Nodes (7): Account Value Over Time (Rp, starting Rp20jt), IHSG Buy & Hold Benchmark (Rp19jt), IDX Mean-Reversion v1 Equity Curve Chart (2020-2026), IDX Mean-Reversion v1 Strategy, Agresif K3 1.5x Series (Rp104jt), Konservatif K5 1x Series (Rp43jt), Seimbang K4 1x Series (Rp48jt)

### Community 25 - "Stock Data Fetcher"
Cohesion: 0.43
Nodes (4): fetch_daily(), _parse(), path_of(), run()

### Community 26 - "IDX Market Data Fetcher"
Cohesion: 0.52
Nodes (6): build(), fetch_stock_summary(), fetch_top_brokers(), last_trading_dates(), list tanggal mundur dari hari ini (skip weekend) utk cari hari-bursa terakhir., sess()

### Community 27 - "Deploy Fetch Research"
Cohesion: 0.43
Nodes (4): fetch_daily(), _parse(), path_of(), run()

### Community 28 - "WhatsApp Baileys Daemon"
Cohesion: 0.33
Nodes (6): app, { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion }, express, fs, pino, start()

### Community 29 - "Fed DCA Research"
Cohesion: 0.40
Nodes (3): base_cfg(), block = bool array, True = jangan entry bar itu., run_block()

### Community 31 - "Regime Filter Verification"
Cohesion: 0.40
Nodes (3): apply_filter(), cperturb(), Return filtered T preserving T0 canonical order (so portfolio greedy matches).

### Community 33 - "Journal Demo Page Logic"
Cohesion: 0.40
Nodes (5): drawShareCard(e) JS function, ENTRIES demo journal data array, renderCalendar() JS function, renderList() JS function, showCard(id) JS function

### Community 34 - "Installer Script"
Cohesion: 0.70
Nodes (4): setup.sh script, ok(), say(), warn()

### Community 35 - "Order Book Recorder"
Cohesion: 0.70
Nodes (4): fetch(), load(), main(), nice_step()

### Community 36 - "Paper Order Book Simulator"
Cohesion: 0.50
Nodes (4): fetch_depth(), orderbook_fill(), Coba direct (Proton ON) -> fallback cors.sh proxy (Proton OFF, Binance ke-block, side: 'buy'/'sell'. Walk book: buy makan asks, sell makan bids.

### Community 38 - "Multi-Timeframe Research"
Cohesion: 0.50
Nodes (3): metrics(), mtf=False -> baseline 5m-grid v20 (harus mendekati +3327). mtf=True -> aktif exi, run_mtf()

### Community 39 - "IHSG Technical Analysis"
Cohesion: 0.70
Nodes (4): analyze(), macd(), main(), stoch()

### Community 42 - "Mainnet Order Book Verification"
Cohesion: 0.60
Nodes (4): get(), main(), Walk order book, return (avg_fill, filled). levels = [[price,amount],...] best-f, sim()

### Community 43 - "Static Demo Generator"
Cohesion: 0.83
Nodes (3): banner(), build_journal(), build_terminal()

### Community 44 - "Real Liquidation Data Fetcher"
Cohesion: 0.83
Nodes (3): build(), get(), main()

### Community 45 - "IDX Foreign Flow History"
Cohesion: 0.83
Nodes (3): main(), sess(), trading_days()

### Community 54 - "Chart TradeBoxes Primitive"
Cohesion: 0.67
Nodes (3): TradeBoxes custom lightweight-charts primitive, TradeBoxes JS class (docs/index.html), TRADES demo v20 trade array (9 trades)

## Ambiguous Edges - Review These
- `Kalender Ekonomi panel (7 hari): ADP Non-Farm, Fed Chairman speaks, ISM Manufacturing PMI, President Trump speaks, Average Hourly Earnings, Non-Farm Employment Change, Unemployment Rate/Claims, each with actual-vs-forecast BTC-impact notes` → `config_server.py (btc-terminal public server, contains journal string references)`  [AMBIGUOUS]
  screenshots/02-terminal-full.png · relation: RELATED_TO_MACRO_SL_WIDENING_EVENTS
- `Trade history list (RIWAYAT - privat, per-trade cards with pamer/edit/hapus actions)` → `Screenshot: PnL share card (referenced by 'pamer' button)`  [AMBIGUOUS]
  screenshots/03-journal-full.png · relation: LINKS_TO
- `PnL share card component (shareable trade result card)` → `Kalender PnL (daily calendar heatmap of PnL)`  [AMBIGUOUS]
  screenshots/05-pnl-share-card.png · relation: opened_from

## Knowledge Gaps
- **52 isolated node(s):** `ping.sh script`, `run_bot.sh script`, `run_stocks.sh script`, `WA_PHONE`, `{ default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion }` (+47 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **16 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Kalender Ekonomi panel (7 hari): ADP Non-Farm, Fed Chairman speaks, ISM Manufacturing PMI, President Trump speaks, Average Hourly Earnings, Non-Farm Employment Change, Unemployment Rate/Claims, each with actual-vs-forecast BTC-impact notes` and `config_server.py (btc-terminal public server, contains journal string references)`?**
  _Edge tagged AMBIGUOUS (relation: RELATED_TO_MACRO_SL_WIDENING_EVENTS) - confidence is low._
- **What is the exact relationship between `Trade history list (RIWAYAT - privat, per-trade cards with pamer/edit/hapus actions)` and `Screenshot: PnL share card (referenced by 'pamer' button)`?**
  _Edge tagged AMBIGUOUS (relation: LINKS_TO) - confidence is low._
- **What is the exact relationship between `PnL share card component (shareable trade result card)` and `Kalender PnL (daily calendar heatmap of PnL)`?**
  _Edge tagged AMBIGUOUS (relation: opened_from) - confidence is low._
- **Why does `send_whatsapp()` connect `Live Bot Execution Engine` to `Private Admin Server`, `AI Commentary Generator`?**
  _High betweenness centrality (0.108) - this node is a cross-community bridge._
- **Why does `gemini_key()` connect `AI Commentary Generator` to `Private Admin Server`?**
  _High betweenness centrality (0.012) - this node is a cross-community bridge._
- **Why does `call_gemini()` connect `AI Commentary Generator` to `Private Admin Server`?**
  _High betweenness centrality (0.011) - this node is a cross-community bridge._
- **What connects `Rangkai snapshot pasar dari endpoint publik SENDIRI (sudah agregasi Binance/news`, `Resolve A-record via Cloudflare DoH (HTTPS) -> IP asli (kebal DNS-hijack ISP). C`, `Relay src->dst. Kalau fragment_first: split kiriman PERTAMA jadi byte-1 + sisany` to the rest of the system?**
  _147 weakly-connected nodes found - possible documentation gaps or missing edges._