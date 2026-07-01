#!/usr/bin/env python3
"""pw_idx.py — tes Playwright tembus Cloudflare IDX (real browser, eksekusi JS challenge).
Di IP Proton. Kalau lolos -> ambil cookie+UA ATAU langsung tarik JSON broksum."""
import json, time, sys
from playwright.sync_api import sync_playwright

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
HOME="https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-broker/"
API="https://www.idx.co.id/primary/TradingSummary/GetBrokerSummary?start=0&length=150"

def run():
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-blink-features=AutomationControlled","--disable-dev-shm-usage"])
        ctx=b.new_context(user_agent=UA, locale="id-ID", viewport={"width":1366,"height":768})
        pg=ctx.new_page()
        pg.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                           "window.chrome={runtime:{}};"
                           "Object.defineProperty(navigator,'languages',{get:()=>['id-ID','id','en']});"
                           "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3]});")
        print("1. goto homepage (solve challenge)...")
        try: pg.goto(HOME, timeout=50000, wait_until="domcontentloaded")
        except Exception as e: print("   goto err:",str(e)[:70])
        time.sleep(8)
        print("   title:", pg.title()[:60])
        ck=ctx.cookies(); cfc=[c["name"] for c in ck if "cf" in c["name"].lower() or "clear" in c["name"].lower()]
        print("   cookies:", len(ck), "| cf-ish:", cfc)
        print("2. tarik API JSON broksum...")
        try:
            pg.goto(API, timeout=50000, wait_until="domcontentloaded"); time.sleep(3)
            body=pg.inner_text("body")
            if "Attention Required" in body or "Just a moment" in body or "<html" in body[:50].lower():
                print("   MASIH BLOCK:", body[:90].replace(chr(10)," "))
            else:
                try:
                    j=json.loads(body); d=j.get("data",[])
                    print(f"   ✅ TEMBUS! rows={len(d)}")
                    if d: print("   sample:",{k:d[0].get(k) for k in list(d[0].keys())[:6]})
                    # simpan cookie utk reuse curl_cffi
                    ckstr="; ".join(f"{c['name']}={c['value']}" for c in ck)
                    json.dump({"cookie":ckstr,"ua":UA}, open("/home/dnayaka/Documents/dynamic_rsi/btc-terminal/stocks/.idx_cookie","w"))
                    print("   cookie disimpan -> .idx_cookie")
                except Exception as e: print("   not JSON:", body[:90].replace(chr(10)," "))
        except Exception as e: print("   api err:",str(e)[:70])
        b.close()

if __name__=="__main__": run()
