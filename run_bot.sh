#!/bin/bash
# Auto-trade BTC bot — dijalankan cron tiap 15m
export WA_PHONE="6289672845575"
# ISI API key Binance utk LIVE trading (IP-restrict, futures-only, no-withdraw):
export BINANCE_KEY=""
export BINANCE_SECRET=""
cd /home/dnayaka/Documents/dynamic_rsi/btc-terminal
python3 bot_v22.py --once >> /home/dnayaka/Documents/dynamic_rsi/btc-terminal/bot_v22.log 2>&1
