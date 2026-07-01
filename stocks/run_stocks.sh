#!/bin/bash
# Sinyal saham IDX (mean-reversion v1) — cron 09:30 & 15:00 WIB. Refresh data + WA alert.
export WA_PHONE="6289672845575"
cd /home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks
python3 signal_stocks.py --update --wa >> /home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks/signal.log 2>&1
