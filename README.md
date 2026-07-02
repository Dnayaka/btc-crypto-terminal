# Crypto Terminal — BTC/ETH/SOL Trading Dashboard

A self-built trading terminal: live chart + custom momentum strategy engine + liquidity visualization + AI commentary + economic calendar, for BTC/ETH/SOL perpetuals. Built as a Bloomberg-terminal-style single-page dashboard (Python stdlib `http.server`, no framework), backed by a Python bot that runs the same strategy logic live. Self-contained and portable (deployable to any VPS).

## Screenshots

| | |
|---|---|
| ![Main terminal](screenshots/01-terminal-main.png) | ![Trading journal + PnL calendar](screenshots/04-journal-pnlcard-calendar.png) |
| Live chart with the v20 strategy overlaid, liquidity panels, market snapshot | Trading journal: total PnL, win rate, month-by-month PnL calendar |
| ![Shareable PnL card](screenshots/05-pnl-share-card.png) | ![Full terminal, all panels](screenshots/02-terminal-full.png) |
| Auto-generated "flex card" per trade, downloadable as PNG | Full page — liquidity, AI read, DXY, economic calendar, macro news, news wire |

*(Numbers shown are synthetic demo data for illustration — not a real track record. See [Safety notes](#safety-notes) below.)*

## Architecture (security-critical split)

| Component | Port | Bind | Purpose |
|---|---|---|---|
| `config_server.py` | :8788 | `0.0.0.0` (public) | **Read-only** market data: chart, liquidity, news, calendar, AI commentary. No keys, no trading. Safe to expose to the internet. |
| `config_admin.py` | :8789 | `127.0.0.1` only | API keys, live/paper toggle, manual trade execution, user management. **Never expose this port.** |
| `bot_v22.py` + `bot_v20_funding.py` + `eng.py` | — | cron (15m) | Executes the v20 strategy live/paper, writes state read by the admin panel. |
| `gen_v20.py` / `btc15m.py` | — | cron (5m) | Regenerate per-symbol strategy chart data (`{sym}_v20.json`) from live klines. |
| `notify_wa.py` + `wa-daemon/` | :18790 | localhost | WhatsApp notifications (Baileys daemon; auth in `wa-daemon/auth`, gitignored). |

Data flow: backend = thin adapters over Binance/news/calendar APIs → JSON. Frontend = `fetch()` + render, no build step.

## What's in here

- **Live chart** (lightweight-charts) with the v20 momentum-breakout strategy overlaid — entry/exit markers, TP/SL zones, per-trade P&L labels — for **BTC, ETH, and SOL independently** (each has its own volatility-normalized parameter set; see `bot_v20_funding.MULTI_PARAMS`).
- **Liquidity/order-book visualization**: synthetic liquidation heatmap (click a zone → assumed entry price + leverage that produces it), real order-book depth walls, bid/ask imbalance, retail vs. whale vs. taker positioning as percentages.
- **`/performa`**: backtest performance page (return/drawdown/Calmar/win-rate + equity curve), tabbed per asset (BTC/ETH/SOL).
- **AI commentary** (Gemini): market read, Fed-event hawkish/dovish summaries cross-checked against DXY/BTC-dominance, all analysis-only — never wired into execution.
- **Economic calendar**: US high-impact events with plain-language "what happens if actual beats/misses forecast" explanations; actual results pulled from BLS (+ ADP via news extraction) as they release.
- **Macro/geopolitical news panel**: war/sanctions/oil-supply-shock headlines that don't come from a scheduled calendar.
- **`/journal`**: per-user trading journal — notes + compressed screenshots, editable, custom date/time, auto-or-manual PnL (entry/exit/leverage → computed live, or override by hand), a monthly PnL calendar heatmap, and a downloadable share card per trade. Private per account; nothing here is visible to other logged-in users.
- Multi-user auth, rate-limiting, DDoS-resistant caching (load-tested to 1000 concurrent requests, 0 errors).

## Quick start

```bash
git clone <this-repo>
cd btc-terminal
./setup.sh
```

That installs Python deps, creates safe-default config (`live: false`, paper mode),
fetches BTC/ETH/SOL historical data, registers systemd services + cron jobs, and
prints an admin login + next steps. It's idempotent — re-run it any time, it only
fills in what's missing and never overwrites config you've already customized. See
"What `setup.sh` does" below for the full list of steps, and "Setup" for what to do
by hand if you'd rather not run it.

## Running it

```bash
cd btc-terminal
python3 config_server.py   # public :8788
python3 config_admin.py    # private :8789 (localhost only)
```

Or via systemd (installed automatically by `setup.sh`, or manually — see below):
```bash
systemctl --user restart bot-config   # public terminal :8788
systemctl --user restart bot-admin    # private admin :8789
systemctl --user restart wa-daemon    # WhatsApp :18790
journalctl --user -u bot-config -f    # tail logs
crontab -l                            # see all scheduled jobs
```

Cron jobs regenerate strategy data every 5 minutes and run the live bot every 15 minutes. **All cron entries must `cd` into this directory first** — scripts use relative file paths; this has been a recurring source of silent failures during development (`setup.sh` handles this for you).

## What `setup.sh` does

1. `pip install -r requirements.txt` (falls back to `--break-system-packages` on externally-managed Python installs).
2. Creates `bot_config.json` / `bot_secrets.json` / `.terminal_pass` from the `.example` templates if they don't exist yet — never overwrites existing ones.
3. Bootstraps one admin account if `users.json` is empty, and prints the password (shown once).
4. Fetches full BTC/ETH/SOL 15m history (`fetch_hist.py`) if the CSVs are missing, then generates the first `{sym}_v20.json` strategy/backtest data.
5. Writes `~/.config/systemd/user/{bot-config,bot-admin}.service` with the correct absolute path for wherever you cloned the repo, enables them, and turns on `loginctl linger` so they survive logout/reboot.
6. If Node.js is present: `npm install` in `wa-daemon/` and registers `wa-daemon.service` (WhatsApp alerts are optional and stay off until you pair the daemon and flip `wa_enabled` in the admin panel).
7. Installs the cron schedule, tagged with a marker comment so re-running the script replaces the block cleanly instead of duplicating it. Any other cron jobs you already had are left untouched.

## Setup (manual, if you'd rather not run `setup.sh`)

Copy the example files and fill in your own values (nothing sensitive is committed — see `.gitignore`):

```bash
cp bot_secrets.example.json bot_secrets.json   # exchange + Gemini API keys + WhatsApp number
cp bot_config.example.json bot_config.json     # live/paper toggle, size, leverage
```

Default is `live: false` (paper trading, zero real orders). Read `CLAUDE.md` (parent `dynamic_rsi/` folder) before touching strategy/execution logic — it documents every validated/rejected variant and the reasoning behind current parameters.

Dependencies: `pip install -r requirements.txt`; for WhatsApp notifications, `cd wa-daemon && npm install`.

## Deploying to a VPS

1. Copy this folder over, then run `./setup.sh` — it derives every path from wherever the repo lives, so there's nothing to hand-edit.
2. Expose the public terminal port if desired; **admin must stay bound to localhost** — put it behind an SSH tunnel if you need remote access to it.

## Roadmap / known gaps (for whoever picks this up next, including future-me)

- **Pine-Script import**: no general Pine→JS converter exists yet. A full one (arbitrary Pine syntax) is a large undertaking — Pine has its own series/state semantics that don't map 1:1 to plain JS. A *narrower* version — recognizing our own strategy template (breakout + pullback + regime-TP conventions used across `version20`–`version25` in the companion strategy repo) and rendering it on this dashboard — is realistic scope; a general-purpose TradingView-replacement importer is not.
- SOL's v20 is shipped with an explicit low-confidence warning in the UI — momentum-breakout historically transfers poorly to SOL (see `CLAUDE.md` in the parent `dynamic_rsi/` folder for the full multi-ticker research).

Already built (previously listed here as gaps, now shipped): configurable equity/leverage/drawdown simulator and buy-and-hold comparison overlay, both on `/performa`.

## Risk controls (circuit breaker + statistical tripwire)

Two independent layers watch the live bot, on top of the 1x leverage cap:

1. **Circuit breaker** — trips on a single extreme point: drawdown-from-peak ≥15%, or ≥6 consecutive losing trades. Flattens the position and forces `live: false`.
2. **Statistical tripwire** — a second, more sensitive layer that watches the *shape* of recent performance, not just extremes. It tracks 4 rolling metrics (41-trade win rate, 41-trade compounded return, 30-trade short-only win rate, drawdown-from-peak) and compares them against the worst values ever observed in the strategy's real 2019–2025 trade history (cross-checked against a TradingView trade-list export, not just the internal backtest). One metric breaching its historical floor cuts order size 50%; two or more breaching *simultaneously* pauses trading entirely — the same reasoning as the breaker above, just triggered earlier and calibrated from data instead of a round number.

Both are config-toggleable (`bot_config.json` → `breaker`/`tripwire`), both default on, and both are silent no-ops in paper mode until you flip `live: true`. See `CLAUDE.md` §10 for the full derivation and validation (a 6-year replay trips it 14 times at tier-1, 0 times at tier-2 — it isn't decorative).

## Safety notes

- `place_market()` and any live execution path require `live: true` in `bot_config.json` (default `false`) — everything is paper/read-only out of the box.
- Leverage is hard-capped at 1x in the execution path regardless of what's configured.
- This is shared as a research/engineering artifact with methodology disclosed, not a "guaranteed profit" black box. See the companion [btc-rsi-momentum](https://github.com/dnayaka/btc-rsi-momentum) repo for the strategy backtests and honesty notes on forward performance.
