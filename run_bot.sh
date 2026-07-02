#!/bin/bash
# Auto-trade bot — run via cron every 15m
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
python3 bot_v22.py --once >> "$DIR/bot_v22.log" 2>&1
