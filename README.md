# BTC TERMINAL — folder mandiri

> 📍 Lokasi: `/home/dnayaka/Documents/dynamic_rsi/btc-terminal/`  ·  HTML dev selanjutnya: **graphify** (lihat CLAUDE.md)
> Fitur terbaru: BTC Dominance (terminal publik) + popup toast/modal (admin).

Semua yang diperlukan untuk **terminal pasar publik + admin trading privat + bot auto + notif WhatsApp** ada di folder ini (`/home/dnayaka/Documents/dynamic_rsi/btc-terminal/`). Self-contained & portable (bisa dipindah ke VPS).

## Isi folder
| File/Folder | Fungsi |
|---|---|
| `config_server.py` | 🌐 **PUBLIC terminal** :8788 — market data read-only (chart/liquidity/news, BTC/ETH/SOL). Aman dishare. |
| `config_admin.py` | 🔒 **PRIVATE admin** :8789 localhost-only — API key + config + manual Buy/Sell. |
| `bot_v22.py` · `bot_v20_funding.py` · `eng.py` | Bot auto (v20 + funding + CVD), dijalankan cron tiap 15m. |
| `notify_wa.py` · `wa-daemon/` | Notif WhatsApp (Baileys daemon :18790, auth tersimpan di wa-daemon/auth). |
| `run_bot.sh` · `ping.sh` | Wrapper cron (bot 15m + heartbeat 30m). |
| `bot_config.json` | config live/size/leverage (diatur via admin). |
| `bot_secrets.json` | API key Binance (chmod 600). |
| `bot_v22_state.json` | posisi/equity bot. |
| `btc_15m_full.csv` · `btc_funding.csv` | data utk threshold CVD/funding bot. |
| `CLAUDE.md` | panduan pengembangan lengkap. |

## Jalanin / kelola (semua service auto-start saat boot)
```bash
systemctl --user restart bot-config   # public terminal :8788
systemctl --user restart bot-admin    # private admin :8789
systemctl --user restart wa-daemon    # WhatsApp :18790
journalctl --user -u bot-config -f    # log
crontab -l                            # cron bot (run_bot.sh 15m, ping.sh 30m)
```

## Akses
- 🌐 Public market terminal: **http://localhost:8788** (boleh dibuka ke LAN/internet)
- 🔒 Private admin (key+trade): **http://localhost:8789** (laptop ini saja)

## Pindah ke VPS / deploy
Folder ini self-contained. Untuk online:
1. copy folder ke VPS, `pip install ccxt requests pandas numpy`, `cd wa-daemon && npm install`
2. update path `/home/dnayaka/Documents/dynamic_rsi/btc-terminal` → path VPS di file .py/.sh/wa-daemon (sed)
3. bikin systemd service / pakai pm2 / cron
4. Public terminal boleh expose; admin TETAP localhost.

Detail dev: lihat `CLAUDE.md`.
