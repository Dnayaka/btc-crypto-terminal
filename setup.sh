#!/usr/bin/env bash
# setup.sh — one-shot installer for the Crypto Terminal.
# Installs deps, creates safe-default config, fetches historical data,
# registers systemd services + cron jobs, then prints next steps.
#
# Safe to re-run any time: every step only fills in what's missing.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

say()  { printf '\n\033[1;33m==> %s\033[0m\n' "$1"; }
ok()   { printf '  \033[1;32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[1;31m!\033[0m %s\n' "$1"; }

say "Crypto Terminal setup — $DIR"

# ---------- 1. Python dependencies ----------
command -v python3 >/dev/null || { echo "python3 is required — install it first"; exit 1; }
say "Installing Python dependencies"
if ! python3 -m pip install --user -q -r requirements.txt 2>/tmp/pip_err.$$; then
  if grep -q "externally-managed-environment" /tmp/pip_err.$$ 2>/dev/null; then
    warn "system Python is externally-managed — retrying with --break-system-packages"
    python3 -m pip install --user --break-system-packages -q -r requirements.txt
  else
    cat /tmp/pip_err.$$; rm -f /tmp/pip_err.$$; exit 1
  fi
fi
rm -f /tmp/pip_err.$$
ok "python dependencies installed"

# ---------- 2. Config files (never overwrite existing) ----------
say "Config files"
if [ ! -f bot_config.json ]; then cp bot_config.example.json bot_config.json; ok "bot_config.json created (paper mode, safe default)"; else ok "bot_config.json already exists, left untouched"; fi
if [ ! -f bot_secrets.json ]; then cp bot_secrets.example.json bot_secrets.json; chmod 600 bot_secrets.json; ok "bot_secrets.json created (empty — fill in via admin panel or edit directly)"; else ok "bot_secrets.json already exists, left untouched"; fi
if [ ! -f .terminal_pass ]; then
  python3 -c "import secrets; open('.terminal_pass','w').write(secrets.token_urlsafe(12))"
  chmod 600 .terminal_pass
  ok ".terminal_pass generated"
else
  ok ".terminal_pass already exists, left untouched"
fi
if [ ! -f vapid_keys.json ]; then
  python3 -c "
from py_vapid import Vapid02
from cryptography.hazmat.primitives import serialization
import base64, json, os
v=Vapid02(); v.generate_keys()
raw=v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
out={'private_pem':v.private_pem().decode(),'public_key':base64.urlsafe_b64encode(raw).rstrip(b'=').decode()}
tmp='vapid_keys.json.tmp'; fd=os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
with os.fdopen(fd,'w') as f: json.dump(out,f)
os.replace(tmp,'vapid_keys.json')
"
  ok "vapid_keys.json generated (browser push notification keypair)"
else
  ok "vapid_keys.json already exists, left untouched"
fi

# ---------- 3. Admin account bootstrap ----------
say "Admin account"
EXISTING_USERS="$(python3 -c 'import userdb; print(len(userdb.load_users()))' 2>/dev/null || echo 0)"
if [ "$EXISTING_USERS" = "0" ]; then
  ADMIN_USER="${TERMINAL_ADMIN_USER:-admin}"
  ADMIN_PASS="${TERMINAL_ADMIN_PASS:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(9))')}"
  python3 -c "import userdb; userdb.bootstrap_admin('$ADMIN_USER', '$ADMIN_PASS')"
  ok "admin account created — SAVE THIS (shown once): $ADMIN_USER / $ADMIN_PASS"
  PRINTED_USER="$ADMIN_USER"; PRINTED_PASS="$ADMIN_PASS"
else
  ok "$EXISTING_USERS account(s) already in users.json, skipping"
  PRINTED_USER="(existing account)"; PRINTED_PASS="(unchanged)"
fi

# ---------- 4. Historical OHLCV + first strategy-data generation ----------
say "Historical data (first run only — a few minutes per symbol)"
for s in BTC ETH SOL; do
  f="$(echo "$s" | tr 'A-Z' 'a-z')_15m_full.csv"
  if [ -s "$f" ]; then
    ok "$f present"
  else
    echo "  fetching ${s}USDT 15m history from Binance..."
    python3 fetch_hist.py "${s}USDT" || warn "fetch ${s} failed — re-run later: python3 fetch_hist.py ${s}USDT"
  fi
done
say "Generating strategy chart/backtest data"
python3 btc15m.py            && ok "btc_v20.json" || warn "btc15m.py failed — check network, re-run later"
python3 gen_v20.py ETHUSDT    && ok "eth_v20.json" || warn "gen_v20.py ETHUSDT failed — re-run later"
python3 gen_v20.py SOLUSDT    && ok "sol_v20.json" || warn "gen_v20.py SOLUSDT failed — re-run later"

# ---------- 5. systemd user services ----------
say "systemd user services (auto-start on boot)"
PY="$(command -v python3)"
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/bot-config.service" <<EOF
[Unit]
Description=Crypto terminal — public UI (:8788)
[Service]
WorkingDirectory=$DIR
ExecStart=$PY $DIR/config_server.py
Restart=always
RestartSec=5
[Install]
WantedBy=default.target
EOF
cat > "$HOME/.config/systemd/user/bot-admin.service" <<EOF
[Unit]
Description=Crypto terminal — private admin (:8789, localhost only)
[Service]
WorkingDirectory=$DIR
ExecStart=$PY $DIR/config_admin.py
Restart=always
RestartSec=5
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now bot-config bot-admin
if command -v loginctl >/dev/null && loginctl enable-linger "$USER" 2>/dev/null; then
  ok "services enabled + linger on (survive logout/reboot)"
else
  ok "services enabled and running"
  warn "could not enable linger automatically — run manually: loginctl enable-linger \$USER"
fi

# ---------- 6. WhatsApp daemon (optional) ----------
if command -v node >/dev/null 2>&1; then
  say "WhatsApp notification daemon (optional)"
  ( cd wa-daemon && npm install --silent )
  cat > "$HOME/.config/systemd/user/wa-daemon.service" <<EOF
[Unit]
Description=Crypto terminal — WhatsApp notification daemon (:18790)
After=network-online.target
[Service]
WorkingDirectory=$DIR/wa-daemon
ExecStart=$(command -v node) $DIR/wa-daemon/index.js
Restart=always
RestartSec=5
[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now wa-daemon
  ok "wa-daemon installed and running — pair your WhatsApp + set the number from the admin panel"
else
  warn "node not found — skipping WhatsApp daemon (optional; install Node.js and re-run this script to enable)"
fi

# ---------- 7. cron jobs (idempotent, tagged so re-runs never duplicate) ----------
say "Cron jobs"
MARK="# crypto-terminal-autogen"
NEWCRON="$(cat <<EOF
1,16,31,46 * * * * cd $DIR && ./run_bot.sh $MARK
*/30 * * * * cd $DIR && ./ping.sh $MARK
*/5 * * * * cd $DIR && python3 btc15m.py >> btc15m.log 2>&1 $MARK
*/5 * * * * cd $DIR && python3 gen_v20.py ETHUSDT >> gen_eth.log 2>&1 $MARK
*/5 * * * * cd $DIR && python3 gen_v20.py SOLUSDT >> gen_sol.log 2>&1 $MARK
*/10 * * * * cd $DIR && python3 ai_gen.py --once >> ai_gen.log 2>&1 $MARK
7 * * * * cd $DIR && python3 cal_fetch.py >> cal_fetch.log 2>&1 $MARK
*/15 * * * * cd $DIR && python3 fed_summary.py >> fed_summary.log 2>&1 $MARK
*/2 * * * * cd $DIR && python3 check_alerts_push.py >> check_alerts_push.log 2>&1 $MARK
EOF
)"
TMPCRON="$(mktemp)"
( crontab -l 2>/dev/null | grep -vF "$MARK" || true ) > "$TMPCRON"
echo "$NEWCRON" >> "$TMPCRON"
crontab "$TMPCRON"
rm -f "$TMPCRON"
ok "cron jobs installed (re-running this script replaces them cleanly, never duplicates)"

say "DONE"
cat <<EOF

  Public terminal : http://localhost:8788   (share this port, read-only market data)
  Private admin   : http://localhost:8789   (localhost only — never expose to the internet)
  Login           : $PRINTED_USER / $PRINTED_PASS

  Still in paper mode (bot_config.json: live=false) — no real or testnet orders yet.
  To go live:
    1. Add Binance API keys via the admin panel (or edit bot_secrets.json).
    2. Validate execution mechanics on testnet first: python3 verify_testnet.py
    3. Read TESTNET_CHECKLIST.md before ever setting net=mainnet.

  Optional:
    - WhatsApp alerts: pair the daemon + set your number from the admin panel
      (Settings), then flip wa_enabled=true.
    - AI commentary (Gemini): add a free key from aistudio.google.com to
      bot_secrets.json field "gemini", or via the admin panel.

  Re-run ./setup.sh any time — it only fills in what's missing and never
  touches config you've already customized.
EOF
