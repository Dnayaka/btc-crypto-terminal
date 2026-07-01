# ✅ Checklist Verifikasi TESTNET → sebelum MAINNET (uang asli)

Tujuan: buktikan **mekanik eksekusi** jalan benar pakai **uang palsu** (Binance testnet)
sebelum sentuh uang asli. Jangan lompat ke mainnet sebelum semua ✅.

---

## FASE 0 — Persiapan (sekali)
- [ ] Daftar akun + API key **Binance Futures TESTNET**: https://testnet.binancefuture.com (login pakai GitHub, lalu "API Key").
- [ ] Buka admin: `http://localhost:8789`
- [ ] Switch **TESTNET** (toggle net, badge jadi amber), paste **testnet key+secret** → Store.
- [ ] Set **Size USD ≥ 100** (min notional Binance), leverage **1x** (terkunci).
- [ ] Cek key tersimpan: panel API Credentials → "● TESTNET key active".

## FASE 1 — Verifikasi mekanik (otomatis, ~30 detik)
- [ ] Di admin: nyalakan **LIVE** (badge `LIVE·TEST` amber — ini testnet, uang palsu).
- [ ] Terminal:
  ```bash
  cd /home/dnayaka/Documents/dynamic_rsi/btc-terminal && python3 verify_testnet.py
  ```
- [ ] Semua PASS: auth ✓, OPEN long qty benar ✓, CLOSE flat (exact-qty) ✓, OPEN short ✓, FLIP ✓, **posisi akhir flat** ✓.
- [ ] Kalau ada FAIL → STOP, benerin dulu, jangan lanjut.

## FASE 2 — Forward run di testnet (beberapa hari)
Biarkan bot jalan via cron (sudah otomatis tiap 15m). Pantau saat **sinyal v20 muncul**:
- [ ] **Order ter-place** saat sinyal: cek `bot_v22.log` + notifikasi **WhatsApp** "✅ TESTNET v20 …".
- [ ] **Posisi di testnet** (cek di testnet.binancefuture.com) cocok dgn arah & qty bot.
- [ ] **Exit**: saat SL/TP/trail kena, bot market-close → posisi flat di testnet, WA masuk.
- [ ] **Rekonsiliasi**: bot `--status` & posisi exchange konsisten (tak ada nyangkut/dobel).
- [ ] **Entry timing** wajar (≈ harga saat sinyal, bukan meleset jauh).
- [ ] Coba **trade manual** dari admin (testnet) → ter-eksekusi + WA. Catat: bot akan reconcile posisi manual di run berikut (kecuali `sleeves.v20=false`).

## FASE 3 — Uji circuit-breaker (opsional tapi disarankan)
- [ ] Turunkan sementara ambang di `bot_config.json` → `"breaker":{"max_loss_streak":2}` (atau `max_dd_pct` kecil).
- [ ] Setelah 2 loss beruntun di testnet → bot **auto LIVE OFF**, posisi diflat, WA "🛑 CIRCUIT BREAKER".
- [ ] `python3 bot_v22.py --resume` lalu nyalakan LIVE lagi manual. Kembalikan ambang ke 6/15.

## FASE 4 — Go / No-Go ke MAINNET
Lanjut HANYA kalau SEMUA ✅:
- [ ] FASE 1 semua PASS (mekanik benar).
- [ ] FASE 2 minimal **3–5 trade** testnet tereksekusi & ter-rekonsiliasi benar.
- [ ] Tidak ada posisi nyangkut / dobel / mismatch sepanjang forward run.
- [ ] WA alert konsisten tiap order & exit.
- [ ] Circuit-breaker terbukti memutus (FASE 3).
- [ ] Kamu paham: slippage exit granularitas-bar = biaya nyata (live ≠ backtest persis).

## FASE 5 — Cutover MAINNET (uang asli, hati-hati)
- [ ] Daftar key **Binance MAINNET asli**: **Futures-only · IP-restricted · NO withdrawal**.
- [ ] Admin: switch **MAINNET** (badge merah), paste key mainnet → Store.
- [ ] **Size kecil dulu** ($100–120), leverage 1x.
- [ ] Nyalakan LIVE → konfirmasi dialog "UANG ASLI".
- [ ] Pantau ketat trade pertama (log + WA + posisi Binance). Naikkan size bertahap kalau yakin.
- [ ] Panik button: matikan LIVE di admin, atau `python3 bot_v22.py --reset` + tutup posisi manual.

---
**Pegangan:** testnet membuktikan *mekanik* (order/close/reconcile). Ia TIDAK membuktikan *profit* —
edge berasal dari strategi v20 yang sudah divalidasi backtest. Mainnet = mulai kecil, naik pelan.
