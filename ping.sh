#!/bin/bash
# Heartbeat every 30m: confirm bot is alive + position status -> WhatsApp
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
WACON=$(curl -s http://127.0.0.1:18790/status 2>/dev/null | grep -q '"connected":true' && echo "WA✅" || echo "WA❌")
STAT=$(python3 bot_v22.py --status 2>/dev/null | grep -E "v20 |fund |cvd |GABUNGAN" | sed 's/^ *//')
python3 notify_wa.py "🟢 Bot hidup $(date '+%H:%M %d/%m') | $WACON
$STAT" >/dev/null 2>&1
