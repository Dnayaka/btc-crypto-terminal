#!/usr/bin/env python3
"""verify_testnet.py — validasi mekanik EKSEKUSI di Binance TESTNET (uang palsu).

AMAN by design:
  - REFUSE jalan kalau net != 'testnet' (tak akan pernah order di mainnet).
  - Selalu flat di akhir (finally), apa pun hasilnya.
Prasyarat (atur di admin :8789): net=TESTNET, LIVE=ON, testnet key terisi, size>=$100.

  python3 verify_testnet.py
"""
import sys, time
import bot_v20_funding as b

def main():
    cfg=b.load_config()
    print("=== VERIFY TESTNET (mekanik eksekusi) ===")
    # ---- SAFETY GATES ----
    if cfg.get("net")!="testnet":
        print(f"❌ BATAL: net='{cfg.get('net')}' bukan 'testnet'. Set net=TESTNET dulu. JANGAN di mainnet."); sys.exit(2)
    if not cfg.get("live"):
        print("❌ BATAL: live=false. Nyalakan LIVE (di testnet) dulu di admin."); sys.exit(2)
    k,s=b.load_keys("testnet")
    if not k or not s:
        print("❌ BATAL: testnet key belum diisi (admin -> net=TESTNET -> Store)."); sys.exit(2)
    sym=cfg.get("symbol","BTC/USDT:USDT"); size=float(cfg.get("size_usd",120))
    df=b.fetch_klines(50)
    if df is None: print("❌ gagal ambil harga (mainnet feed)."); sys.exit(1)
    price=float(df['close'].iloc[-1]); tgt=round(size/price,3); tol=max(0.001,0.05*tgt)
    print(f"net=TESTNET | size=${size:.0f} | price~${price:.0f} | target~{tgt} BTC")
    if tgt*price < 100: print(f"⚠️ notional ${tgt*price:.0f} < min $100 — naikkan size dulu."); sys.exit(1)

    ex=b._exchange("testnet")
    P=[];F=[]
    def ck(n,c,d=""):
        (P if c else F).append(n); print(f"  [{'PASS' if c else 'FAIL'}] {n}"+("" if c else f"  — {d}"))
    def settle(): time.sleep(2.5); return b.read_position(ex,sym)
    try:
        bal=ex.fetch_balance()
        ck("auth + konektivitas (fetch_balance)", isinstance(bal,dict))
        start=b.read_position(ex,sym); print(f"  posisi awal: {start:+.3f}")
        if abs(start)>1e-9:
            print("  (flatten posisi awal dulu…)"); b.sync_live("verify",0,price); settle()
        b.sync_live("verify",1,price);  p=settle(); ck("OPEN long (+1) -> qty benar", abs(p-tgt)<=tol, f"pos={p:+.3f} tgt={tgt}")
        b.sync_live("verify",0,price);  p=settle(); ck("CLOSE -> flat (reduceOnly qty aktual)", abs(p)<=0.0009, f"pos={p:+.3f}")
        b.sync_live("verify",-1,price); p=settle(); ck("OPEN short (-1) -> qty benar", abs(p+tgt)<=tol, f"pos={p:+.3f}")
        b.sync_live("verify",1,price);  p=settle(); ck("FLIP short->long -> qty benar", abs(p-tgt)<=tol, f"pos={p:+.3f}")
    except Exception as e:
        ck("eksekusi tanpa exception", False, str(e)[:140])
    finally:
        print("  cleanup -> flat…"); b.sync_live("verify",0,price); time.sleep(2.5)
        fin=b.read_position(ex,sym)
        print(f"  posisi akhir: {fin:+.3f}", "✓ flat" if abs(fin)<=0.0009 else "⚠️ MASIH ADA POSISI — TUTUP MANUAL!")
    print(f"\nHASIL: PASS {len(P)} / FAIL {len(F)}")
    if F:
        print("❌ Ada yang gagal — benerin SEBELUM pertimbangkan mainnet:"); [print("   -",x) for x in F]; sys.exit(1)
    print("✅ Mekanik eksekusi TESTNET valid (auth, open, close exact-qty, flip, reconcile, flat).")

if __name__=="__main__": main()
