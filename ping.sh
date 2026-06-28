#!/bin/bash
# Heartbeat 30-menit: konfirmasi bot hidup + status posisi -> WhatsApp
export WA_PHONE="6289672845575"
cd /home/dnayaka/Documents/dynamic_rsi/btc-terminal
WACON=$(curl -s http://127.0.0.1:18790/status 2>/dev/null | grep -q '"connected":true' && echo "WA✅" || echo "WA❌")
STAT=$(python3 bot_v22.py --status 2>/dev/null | grep -E "v20 |fund |cvd |GABUNGAN" | sed 's/^ *//')
python3 notify_wa.py "🟢 Bot hidup $(date '+%H:%M %d/%m') | $WACON
$STAT" >/dev/null 2>&1
