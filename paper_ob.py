#!/usr/bin/env python3
"""paper_ob.py — PAPER fill realistis: simulasi market order NABRAK ORDERBOOK ASLI mainnet
Binance (walk the book) -> harga fill rata2 + slippage + apakah depth cukup. NOL uang asli.

orderbook_fill(side,qty_btc) -> {avg_px, slip_pct, filled, depth_btc, levels_used, notional}
"""
import json, requests, urllib3, time
urllib3.disable_warnings()
S=requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0"}); FAPI="https://fapi.binance.com"

def fetch_depth(symbol="BTCUSDT", limit=1000):
    """Coba direct (Proton ON) -> fallback cors.sh proxy (Proton OFF, Binance ke-block ISP)."""
    path=f"/fapi/v1/depth?symbol={symbol}&limit={limit}"
    for url in (FAPI+path, "https://proxy.cors.sh/"+FAPI+path):
        try:
            r=S.get(url, timeout=15, verify=False); j=r.json()
            if isinstance(j,dict) and j.get("bids") and j.get("asks"): return j   # H1: wajib non-kosong
        except Exception: pass
    raise RuntimeError("depth gagal (direct + cors.sh)")

def orderbook_fill(side, qty_btc, symbol="BTCUSDT", ob=None):
    """side: 'buy'/'sell'. Walk book: buy makan asks, sell makan bids."""
    ob = ob or fetch_depth(symbol)
    levels = ob["asks"] if side=="buy" else ob["bids"]   # [[price,qty],...] asc(asks)/desc(bids)
    if not levels: raise RuntimeError("orderbook kosong (sisi "+side+")")   # H1: guard empty
    best=float(levels[0][0]); rem=float(qty_btc); cost=0.0; used=0.0; n=0
    depth=sum(float(a) for _,a in levels)
    for price,amt in levels:
        price=float(price); amt=float(amt); take=min(rem,amt)
        cost+=take*price; used+=take; rem-=take; n+=1
        if rem<=1e-12: break
    filled = rem<=1e-9
    avg = cost/used if used>0 else best
    slip = (avg/best-1)*100*(1 if side=="buy" else -1)   # + = kena slippage merugikan
    return dict(side=side, qty=round(float(qty_btc),4), best=round(best,1), avg_px=round(avg,2),
                slip_pct=round(slip,4), filled=filled, depth_btc=round(depth,2),
                depth_left=round(rem,4), levels_used=n, notional=round(used*avg,0))

if __name__=="__main__":
    ob=fetch_depth()
    print(f"orderbook BTCUSDT.P (mainnet) | best bid {ob['bids'][0][0]} / ask {ob['asks'][0][0]} | depth {len(ob['asks'])} lvl/sisi")
    for usd in [100, 1000, 100000, 1000000, 20000000]:
        px=float(ob['asks'][0][0]); q=usd/px
        f=orderbook_fill("buy", q, ob=ob)
        tag="✅ muat" if f['filled'] else f"❌ HABIS (sisa {f['depth_left']} BTC)"
        print(f"  BUY ${usd:>10,}: {q:.4f} BTC -> avg {f['avg_px']:.1f} slip {f['slip_pct']:+.4f}% ({f['levels_used']} lvl) {tag}")
