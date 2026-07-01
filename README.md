# Crypto Terminal — BTC/ETH/SOL Trading Dashboard

A self-built trading terminal: live chart + custom momentum strategy engine + liquidity visualization + AI commentary + economic calendar, for BTC/ETH/SOL perpetuals. Built as a Bloomberg-terminal-style single-page dashboard (Python stdlib `http.server`, no framework), backed by a Python bot that runs the same strategy logic live. Self-contained and portable (deployable to any VPS).

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
- Multi-user auth, rate-limiting, DDoS-resistant caching (load-tested to 1000 concurrent requests, 0 errors).

## Running it

```bash
cd btc-terminal
python3 config_server.py   # public :8788
python3 config_admin.py    # private :8789 (localhost only)
```

Or via systemd (auto-start on boot):
```bash
systemctl --user restart bot-config   # public terminal :8788
systemctl --user restart bot-admin    # private admin :8789
systemctl --user restart wa-daemon    # WhatsApp :18790
journalctl --user -u bot-config -f    # tail logs
crontab -l                            # see all scheduled jobs
```

Cron jobs regenerate strategy data every 5 minutes and run the live bot every 15 minutes. **All cron entries must `cd` into this directory first** — scripts use relative file paths; this has been a recurring source of silent failures during development.

## Setup

Copy the example files and fill in your own values (nothing sensitive is committed — see `.gitignore`):

```bash
cp bot_secrets.example.json bot_secrets.json   # exchange + Gemini API keys
cp bot_config.example.json bot_config.json     # live/paper toggle, size, leverage
```

Default is `live: false` (paper trading, zero real orders). Read `CLAUDE.md` (parent `dynamic_rsi/` folder) before touching strategy/execution logic — it documents every validated/rejected variant and the reasoning behind current parameters.

Dependencies: `pip install ccxt requests pandas numpy`; for WhatsApp notifications, `cd wa-daemon && npm install`.

## Deploying to a VPS

1. Copy this folder over, install dependencies (above).
2. Update the hardcoded base path (`/home/dnayaka/Documents/dynamic_rsi/btc-terminal`) across `.py`/`.sh` files and `wa-daemon/` to your VPS path.
3. Set up systemd services (or pm2) + cron, mirroring the local setup.
4. Expose the public terminal port if desired; **admin must stay bound to localhost** — put it behind an SSH tunnel if you need remote access to it.

## Roadmap / known gaps (for whoever picks this up next, including future-me)

- **Pine-Script import**: no general Pine→JS converter exists yet. A full one (arbitrary Pine syntax) is a large undertaking — Pine has its own series/state semantics that don't map 1:1 to plain JS. A *narrower* version — recognizing our own strategy template (breakout + pullback + regime-TP conventions used across `version20`–`version25` in the companion strategy repo) and rendering it on this dashboard — is realistic scope; a general-purpose TradingView-replacement importer is not.
- **Configurable equity/leverage/drawdown simulator on `/performa`**: not yet built. The trade-level data (`{sym}_v20.json` → `trades[]`) already has everything needed (entry/exit/net-return per trade) to let a user punch in starting equity + leverage and see a scaled equity curve + realistic liquidation-adjusted drawdown, without re-running the backtest engine.
- **Buy-and-hold comparison overlay**: not yet built. Straightforward — same OHLC data already fetched for the chart, compute `equity[t] = price[t]/price[0]` and plot alongside the strategy curve.
- SOL's v20 is shipped with an explicit low-confidence warning in the UI — momentum-breakout historically transfers poorly to SOL (see `CLAUDE.md` in the parent `dynamic_rsi/` folder for the full multi-ticker research).

## Safety notes

- `place_market()` and any live execution path require `live: true` in `bot_config.json` (default `false`) — everything is paper/read-only out of the box.
- Leverage is hard-capped at 1x in the execution path regardless of what's configured.
- This is shared as a research/engineering artifact with methodology disclosed, not a "guaranteed profit" black box. See the companion [btc-rsi-momentum](https://github.com/dnayaka/btc-rsi-momentum) repo for the strategy backtests and honesty notes on forward performance.
