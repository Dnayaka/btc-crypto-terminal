#!/usr/bin/env python3
"""verify_mainnet.py — validasi LAWAN BINANCE ASLI (mainnet) tapi READ-ONLY / DRY-RUN.
Lihat order book NYATA + simulasi fill/slippage utk size kamu + cek auth & posisi (kalau ada key mainnet).
TIDAK pernah menempatkan order. Nol risiko uang. (Order book = data publik, jalan tanpa key.)

  python3 verify_mainnet.py
"""
import sys, requests, urllib3
import bot_v20_funding as b
urllib3.disable_warnings()
FAPI="https://fapi.binance.com"; SYM="BTCUSDT"

def get(path, **p):
    r=requests.get(FAPI+path, params=p, timeout=15, verify=b.VERIFY); r.raise_for_status(); return r.json()

def sim(levels, qty):
    """Walk order book, return (avg_fill, filled). levels = [[price,amount],...] best-first."""
    filled=cost=0.0
    for px,amt in levels:
        take=min(qty-filled, amt); cost+=take*px; filled+=take
        if filled>=qty-1e-12: break
    return (cost/qty, filled) if filled>=qty-1e-12 else (None, filled)

def main():
    cfg=b.load_config(); size=float(cfg.get("size_usd",120))
    print("=== VERIFY MAINNET — READ-ONLY (order book asli · TANPA order · nol risiko) ===\n")

    # 1) ORDER BOOK NYATA
    d=get("/fapi/v1/depth", symbol=SYM, limit=50)
    bids=[[float(p),float(q)] for p,q in d["bids"]]
    asks=[[float(p),float(q)] for p,q in d["asks"]]
    if not bids or not asks: raise SystemExit("orderbook kosong — depth gagal")   # H1 guard
    bb,ba=bids[0][0],asks[0][0]; mid=(bb+ba)/2; spr=ba-bb
    print(f"ORDER BOOK {SYM}   mid ${mid:,.1f}   spread ${spr:.2f} ({spr/mid*1e4:.1f} bp)")
    ca=0; arows=[]
    for p,q in asks[:8]: ca+=q; arows.append((p,q,ca))
    for p,q,c in reversed(arows): print(f"  ask {p:>11,.1f}  {q:>7.3f}   Σ{c:6.2f}")
    print(f"      {'─'*30}  spread ${spr:.2f}")
    cbid=0
    for p,q in bids[:8]: cbid+=q; print(f"  bid {p:>11,.1f}  {q:>7.3f}   Σ{cbid:6.2f}")

    # 2) SIMULASI FILL utk size kita (lawan book asli)
    qty=round(size/mid,3); notion=qty*mid
    bavg,_=sim(asks,qty); savg,_=sim(bids,qty)
    print(f"\nSIMULASI MARKET ORDER (size ${size:.0f} → {qty} BTC, notional ${notion:.0f}):")
    if bavg: print(f"  BUY  fill ~${bavg:,.2f}   slippage {(bavg-mid)/mid*1e4:+.2f} bp")
    if savg: print(f"  SELL fill ~${savg:,.2f}   slippage {(mid-savg)/mid*1e4:+.2f} bp")
    tot_top=sum(q for _,q in asks[:1])
    print(f"  qty {qty} BTC vs depth best-ask {tot_top:.3f} BTC → {'isi di best level, slippage ~0 (likuiditas tebal)' if qty<=tot_top else 'butuh >1 level'}")

    # 3) FILTER SYMBOL (presisi & min notional asli)
    info=get("/fapi/v1/exchangeInfo")
    srow=[x for x in info["symbols"] if x["symbol"]==SYM][0]
    flt={f["filterType"]:f for f in srow["filters"]}
    step=float(flt["LOT_SIZE"]["stepSize"]); mn=flt.get("MIN_NOTIONAL",{})
    minnot=float(mn.get("notional", mn.get("minNotional", 100)))
    okstep=abs(round(qty/step)*step-qty)<1e-9
    print(f"\nFILTER {SYM}: lot step {step} · min notional ${minnot:.0f}")
    print(f"  qty {qty} kelipatan step? {'✓' if okstep else '✗'}   notional ${notion:.0f} ≥ ${minnot:.0f}? {'✓' if notion>=minnot else '✗ NAIKKAN SIZE'}")

    # 4) AUTH + POSISI (read-only, hanya kalau ada key mainnet)
    k,s=b.load_keys("mainnet")
    print()
    if k and s:
        try:
            ex=b._exchange("mainnet")               # mainnet asli (BUKAN sandbox)
            usdt=(ex.fetch_balance().get("USDT") or {}).get("total")
            posn=b.read_position(ex, cfg.get("symbol","BTC/USDT:USDT"))
            print(f"AUTH MAINNET ✓  saldo USDT {usdt}  posisi BTC sekarang {posn:+.3f}")
            print("  (read-only: fetch_balance + fetch_positions — NOL order ditempatkan)")
        except Exception as e:
            print("AUTH MAINNET gagal:", str(e)[:140])
    else:
        print("AUTH/POSISI dilewati (belum ada key mainnet). Order book & simulasi di atas tetap valid (publik).")

    print("\n⚠️ READ-ONLY: ini lihat data asli + simulasi, TIDAK menempatkan order.")
    print("   Buktiin FILL beneran butuh 1 order kecil asli (~$100) — keputusanmu, kabari kalau mau.")

if __name__=="__main__": main()
