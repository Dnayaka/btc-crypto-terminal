#!/usr/bin/env python3
"""signal_stocks.py — generator sinyal harian formula IDX Mean-Reversion v1.
Cari saham yg BUY-signal di bar terakhir (beli next-open) + saham yg EXIT-signal, + konteks IHSG.
Output stocks_signal.json (dibaca UI nanti) + opsional alert WhatsApp.

  python3 signal_stocks.py            # pakai data cached (cepat)
  python3 signal_stocks.py --update   # refresh data universe dulu (incremental), lalu sinyal
  python3 signal_stocks.py --wa       # kirim ringkasan ke WhatsApp
"""
import os, sys, json, time
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seng, pf, mflow
HERE=os.path.dirname(os.path.abspath(__file__))

FINAL=dict(pf.CAND); FINAL.update(rsi_len=4, rsi_buy=15.0, rsi2_or=0.0,
            req_sma50_rising=True, sma50_rise_win=5, min_volval=1e10)
DEFAULT_K=4   # setelan default user (seimbang)

def update_data():
    """Incremental: tambah bar baru ke CSV cached (1 request kecil/simbol)."""
    from fetch_stocks import fetch_daily, path_of, INDEX, UNIVERSE
    syms=[INDEX]+UNIVERSE
    # + simbol mid-cap tambahan yg sudah ada di data/ (dari workflow deploy)
    import glob
    for f in glob.glob(os.path.join(HERE,"data","*.JK.csv")):
        s=os.path.basename(f)[:-4]
        if s not in syms: syms.append(s)
    upd=0
    for s in syms:
        p=path_of(s) if s==INDEX else os.path.join(HERE,"data",s+".csv")
        try: old=pd.read_csv(p,parse_dates=['dt'])
        except Exception: old=None
        since=(old['dt'].iloc[-1].strftime("%Y-%m-%d") if old is not None else "2020-01-01")
        df,info=fetch_daily(s, since=since)
        if df is not None and len(df):
            if old is not None:
                df=pd.concat([old,df]).drop_duplicates(subset=['dt'],keep='last').sort_values('dt').reset_index(drop=True)
            df.to_csv(p,index=False); upd+=1
        time.sleep(1.0)
    print(f"  update: {upd}/{len(syms)} simbol")

def scan():
    pf._CACHE=None; data=pf.load_data()
    cf=dict(seng.DEF); cf.update(FINAL)   # lengkapi semua key default engine
    import datetime as _dt
    today_wib=(_dt.datetime.utcnow()+_dt.timedelta(hours=7)).date()   # C3: jam WIB
    buys=[]; exits=[]; cand=[]
    for sym,df in data.items():
        df=df[df['dt'].dt.date < today_wib].reset_index(drop=True)   # C3: buang bar HARI INI (belum tutup) -> sinyal di close settled
        if len(df)<260: continue
        ind=seng.indicators(df,cf); ent,ex=seng.entry_exit(df,cf,ind)
        c=ind['c']; St=ind['St']; Sf=ind['Sf']; R=ind['R']; last=len(c)-1
        mf=mflow.snapshot(df)   # money-flow (MFI/CMF/buy-sell %) sekali per saham
        if ent[last]:
            buys.append(dict(sym=sym, close=round(float(c[last]),1),
                             rsi4=round(float(R[last]),1),
                             dist_sma200=round(float((c[last]/St[last]-1)*100),1),
                             dist_sma5=round(float((c[last]/ind['Se'][last]-1)*100),1),
                             volval_m=round(float(ind['volval'][last]/1e9),1), **mf))
        elif (ind['volval'][last]>=1e10) and (c[last]>=50):
            # KANDIDAT WATCHLIST: saham likuid ter-screen, diurut dari yg paling dekat trigger
            up=bool(c[last]>St[last]); rising=bool(Sf[last]>Sf[last-5])
            cand.append(dict(sym=sym, close=round(float(c[last]),1), rsi4=round(float(R[last]),1),
                             to_trigger=round(float(R[last]-15),1),
                             dist_sma200=round(float((c[last]/St[last]-1)*100),1),
                             volval_m=round(float(ind['volval'][last]/1e9),1),
                             uptrend=up, rising=rising, ready=bool(up and rising), **mf))
        if ex[last]:  # info exit utk yg sedang pegang
            exits.append(sym)
    buys.sort(key=lambda x:x['rsi4'])   # paling oversold dulu
    # watchlist: yg sudah uptrend+SMA50-naik dulu, lalu RSI terendah (paling dekat trigger)
    cand.sort(key=lambda x:(not x['ready'], not x['uptrend'], x['rsi4']))
    return buys, exits, cand[:24]

def ai_bandar(items):
    """SATU call Gemini utk SEMUA saham sekaligus (hemat API): interpretasi bandarmology dari
    money-flow. BUKAN broksum kode-broker asli (itu premium) — interpretasi AI atas MFI/CMF/buy-sell%."""
    try:
        sys.path.insert(0, os.path.dirname(HERE))
        from gemini import call_gemini, extract_json, gemini_key
    except Exception: return None
    if not gemini_key() or not items: return None
    rows=[f"{it['sym'].replace('.JK','')}: harga {it.get('close')}, ASING-NET {it.get('foreign_net')}M (Rp miliar, +beli/-jual), "
          f"MFI {it.get('mfi')}, CMF {it.get('cmf')}, buy/sell vol {it.get('buy_pct')}/{it.get('sell_pct')}%, "
          f"hari-vol-besar akum/dist {it.get('big_acc')}/{it.get('big_dist')}, OBV-trend {it.get('obv_tr')}%, "
          f"{it.get('diverg')}, inferensi {it.get('sm')}, RSI4 {it.get('rsi4')}, "
          f"{'+' if (it.get('dist_sma200') or 0)>=0 else ''}{it.get('dist_sma200')}% vs SMA200" for it in items]
    prompt=("Kamu analis bandarmology saham IDX yang TAJAM. Untuk TIAP saham, beri analisa MENDALAM 2 kalimat: "
            "(1) siapa yang menggerakkan — SMART-MONEY/ASING/institusi vs RITEL — pakai ASING-NET (foreign flow NYATA: + = asing borong/smart-money masuk, - = asing buang) + pola volume (OBV, hari-vol-besar, divergence); "
            "(2) fase Wyckoff (akumulasi/markup/distribusi/markdown) + apa yang diwaspadai. "
            "ASING-NET = data IDX ASLI. Sisanya inferensi price+volume. JANGAN mengarang kode broker spesifik. JANGAN saran beli/jual. Bahasa Indonesia, padat.\n"
            'Balas HANYA JSON valid: {"<SYM>":"<2 kalimat>", ..., "_overall":"<2 kalimat: tekanan SM vs ritel di pasar + sektor yang diakumulasi/didistribusi>"}.\n\nDATA:\n'
            + "\n".join(rows))
    txt,err=call_gemini(prompt, max_tokens=2200, temp=0.5)
    d=extract_json(txt) if txt else None
    return d if d else {"_overall":"AI bandar gagal: "+(err or "?")}

def main():
    if "--update" in sys.argv:
        print("refresh data universe ..."); update_data()
    # IHSG TA
    try:
        import ihsg_ta
        ix=pd.read_csv(os.path.join(HERE,"data","_JKSE.csv"),parse_dates=['dt']); ta=ihsg_ta.analyze(ix)
    except Exception as e:
        ta={"bias":"?","regime":"?","price":None}; print("ihsg ta gagal:",e)
    buys,exits,watch=scan()
    # merge NET FOREIGN FLOW (asing) dari idx_summary.json (IDX GetStockSummary, Proton-off) = bandarmology REAL
    ix={}
    try: ix=json.load(open(os.path.join(HERE,"idx_summary.json")))
    except Exception: pass
    idxs=ix.get("stocks",{})
    for it in buys+watch:
        st=idxs.get(it["sym"].replace(".JK",""))
        if st: it["foreign_net"]=st.get("foreign_net")   # Rp miliar, + = asing beli
    out=dict(ts=int(time.time()),
             ihsg=dict(price=ta.get('price'),regime=ta.get('regime'),bias=ta.get('bias'),score=ta.get('score')),
             default_K=DEFAULT_K, n_buy=len(buys), buys=buys, exits=exits,
             n_watch=len(watch), watchlist=watch[:24],
             top_brokers=ix.get("top_brokers",[]), idx_date=ix.get("_date"),
             market_foreign_net=ix.get("market_foreign_net"), top_fbuy=ix.get("top_fbuy",[]), top_fsell=ix.get("top_fsell",[]),
             formula="IDX Mean-Reversion v1 (RSI4<15 & SMA50-naik & >SMA200, likuid)")
    if "--ai" in sys.argv:
        print("  AI bandar (1 batch call Gemini) ...")
        bandar=ai_bandar(buys+watch)
        if bandar: out['ai_bandar']=bandar; out['ai_bandar_ts']=int(time.time()); print("    ai_bandar:",len(bandar)-1,"saham +overall")
    import math
    def _jsafe(o):
        if isinstance(o,float): return None if (math.isnan(o) or math.isinf(o)) else o
        if isinstance(o,dict): return {k:_jsafe(v) for k,v in o.items()}
        if isinstance(o,list): return [_jsafe(x) for x in o]
        return o
    json.dump(_jsafe(out), open(os.path.join(HERE,"stocks_signal.json"),"w"), indent=1)
    # cetak
    print(f"\n=== SINYAL HARIAN · IDX Mean-Reversion v1 ===")
    print(f"  IHSG {ta.get('price')} · {ta.get('regime')} · bias {ta.get('bias')}")
    if buys:
        print(f"  🟢 {len(buys)} KANDIDAT BELI (beli di open besok, bagi {DEFAULT_K} slot):")
        for b in buys[:15]:
            print(f"     {b['sym']:9s} @ {b['close']:>8.0f}  RSI4 {b['rsi4']:>4}  ({b['dist_sma200']:+.0f}% vs SMA200)  likuid Rp{b['volval_m']}M/hr")
    else:
        print(f"  ⚪ TIDAK ADA kandidat beli hari ini (wajar saat IHSG {ta.get('regime')} — formula nahan cash).")
    if watch: print(f"  👁  Watchlist ter-screen ({len(watch)}, belum sinyal): "+", ".join(w['sym'].replace('.JK','')+f"(RSI{w['rsi4']})" for w in watch[:10]))
    if exits: print(f"  🔴 EXIT-signal (jual kalau pegang): {', '.join(exits)}")
    print(f"  -> stocks_signal.json ditulis.")
    if "--wa" in sys.argv:
        try:
            sys.path.insert(0,os.path.dirname(HERE)); from notify_wa import send_whatsapp
            msg=f"📊 Sinyal Saham IDX ({pd.Timestamp.now(tz='Asia/Jakarta').strftime('%d/%m %H:%M')})\nIHSG {ta.get('regime')} (bias {ta.get('bias')})\n"
            msg+= (f"🟢 {len(buys)} beli: "+", ".join(b['sym'].replace('.JK','') for b in buys[:10])) if buys else "⚪ Tidak ada sinyal beli (cash)."
            if exits: msg+=f"\n🔴 Exit: "+", ".join(e.replace('.JK','') for e in exits[:10])
            send_whatsapp(msg)
        except Exception as e: print("  WA gagal:",e)

if __name__=="__main__": main()
