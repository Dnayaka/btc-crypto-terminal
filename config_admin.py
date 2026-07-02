#!/usr/bin/env python3
"""PRIVATE ADMIN — kontrol trading (key/config/execute). LOCALHOST ONLY :8789. JANGAN expose ke publik."""
import json, os, requests, urllib3, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
urllib3.disable_warnings()
HERE="/home/dnayaka/Documents/dynamic_rsi/btc-terminal"; CFG=HERE+"/bot_config.json"; STATE=HERE+"/bot_v22_state.json"; SEC=HERE+"/bot_secrets.json"; FEDLIVE=HERE+"/fed_live.json"
S=requests.Session(); FAPI="https://fapi.binance.com"
import threading
_TRADE_LK=threading.Lock(); _JOB={"stocks":False}   # M4: serialize trade; S4: single-flight refresh
from gemini import call_gemini, gemini_key
from userdb import list_users, add_user, del_user, set_expiry, load_users   # kelola user terminal publik
from config_server import CSS as _PFCSS, HEAD as _PFHEAD, ATMOS as _PFATMOS   # reuse styling utk /performa (PINDAH dari publik ke admin)
def second_opinion():
    """Komentar AI NETRAL soal posisi/sinyal bot v20 saat ini (analisa, BUKAN saran trade)."""
    if not gemini_key(): return {"ok":False,"text":"Gemini key belum diisi (panel API Credentials)."}
    try: v=json.load(open(STATE)).get("v20",{})
    except: v={}
    pos={1:"LONG",-1:"SHORT",0:"FLAT"}.get(v.get("pos",0),"FLAT")
    price=fund=0.0
    try:
        m=S.get(FAPI+"/fapi/v1/premiumIndex?symbol=BTCUSDT",timeout=8,verify=False).json()
        price=float(m["markPrice"]); fund=float(m["lastFundingRate"])*100
    except: pass
    at=(" @ "+str(round(v.get("entry",0)))) if v.get("pos") else ""
    prompt=(f"Bot trading BTC 'v20' (momentum RSI-breakout) saat ini {pos}{at}, "
            f"equity x{v.get('equity',1):.3f}, {v.get('ntr',0)} trade total. "
            f"Harga BTC ~${price:.0f}, funding {fund:+.3f}%/8j. "
            "Beri 2-3 kalimat 'second opinion' NETRAL soal konteks & risiko posisi ini (bahasa Indonesia). "
            "JANGAN kasih perintah beli/jual/leverage — cuma observasi pasar.")
    txt,err=call_gemini(prompt, max_tokens=300)
    return {"ok":bool(txt),"text":txt or ("Gemini gagal: "+(err or "?"))}
def load():
    try: return json.load(open(CFG))
    except: return {"live":False,"net":"testnet","size_usd":100,"leverage":1,"symbol":"BTC/USDT:USDT","sleeves":{"v20":True},"max_size_usd":2000,"wa_enabled":False}
def save(c): json.dump(c,open(CFG,"w"),indent=2)

def _yt_video_id(s):
    """Terima URL YouTube (watch/live/youtu.be/embed) ATAU raw video-id (11 char) -> video-id bersih, else ''."""
    import re
    s=(s or "").strip()
    if not s: return ""
    for pat in (r"(?:v=|youtu\.be/|/live/|/embed/)([A-Za-z0-9_-]{11})", r"^([A-Za-z0-9_-]{11})$"):
        m=re.search(pat, s)
        if m: return m.group(1)
    return ""
def load_fedlive():
    try: return json.load(open(FEDLIVE))
    except Exception: return {"video_id":"","label":"","ts":0}
def save_fedlive(video_id, label):
    d={"video_id":video_id,"label":label,"ts":int(datetime.datetime.now().timestamp())}
    tmp=FEDLIVE+".tmp"; json.dump(d,open(tmp,"w")); os.replace(tmp,FEDLIVE); return d
def load_keys(net="mainnet"):
    """Per-net: {"mainnet":{key,secret},"testnet":{key,secret}}. Backward-compat flat = mainnet."""
    try:
        s=json.load(open(SEC))
        if isinstance(s.get(net),dict): return s[net].get("key",""),s[net].get("secret","")
        if "key" in s and net=="mainnet": return s.get("key",""),s.get("secret","")
    except: pass
    return "",""
def place_market(side):
    c=load(); net=c.get("net","testnet"); k,sec=load_keys(net)
    if net not in ("mainnet","testnet"): return {"ok":False,"msg":f"net invalid '{net}' — refuse"}  # M6 fail-closed
    tag="MAINNET" if net=="mainnet" else "TESTNET"
    if side not in ("buy","sell"): return {"ok":False,"msg":"side invalid"}
    if not c.get("live",False): return {"ok":False,"msg":"Mode PAPER — aktifkan LIVE dulu utk order asli"}
    if not k or not sec: return {"ok":False,"msg":f"API key {tag} belum diisi"}
    lev=max(1,min(1,int(c.get("leverage",1))))                                   # M3: clamp DI EKSEKUSI
    size_usd=min(float(c.get("size_usd",100)),float(c.get("max_size_usd",2000)))  # M3: cap notional
    try:
        import ccxt
        price=float(S.get(FAPI+"/fapi/v1/ticker/price?symbol=BTCUSDT",timeout=10,verify=False).json()["price"])
        qty=round(size_usd*lev/price,3); notional=qty*price
        if notional<100: return {"ok":False,"msg":f"${notional:.0f} < min $100"}
        ex=ccxt.binanceusdm({"apiKey":k,"secret":sec,"enableRateLimit":True,"options":{"defaultType":"future"}})
        ex.has['fetchCurrencies']=False   # skip sapi spot (testnet ga punya; futures-only)
        if net=="mainnet":                # mainnet via proxy lokal anti-DPI (no VPN)
            import os as _os; _px=_os.environ.get("BINANCE_PROXY","socks5h://127.0.0.1:1080")
            if _px:
                try: ex.socksProxy=_px
                except Exception: ex.proxies={"http":_px,"https":_px}
        if net!="mainnet":   # ccxt drop set_sandbox_mode futures -> override URL testnet manual
            api=ex.urls.get('api',{})
            if isinstance(api,dict):
                for kk,vv in list(api.items()):
                    if isinstance(vv,str): api[kk]=vv.replace('fapi.binance.com','testnet.binancefuture.com')
        try: ex.set_position_mode(False)               # M5: one-way
        except: pass
        try: ex.set_leverage(lev,c["symbol"])
        except: pass
        _cid=(f"manual-{int(datetime.datetime.now().timestamp()//5)}-{side}")[:36]   # M4 defense: dedup double-click <5s (Binance tolak cid dobel)
        ex.create_order(c["symbol"],"market",side,qty,params={"newClientOrderId":_cid})
        msg=f"[{tag}] FILLED {side.upper()} {qty} BTC ~${notional:.0f} @ {price:.0f}"
        try:
            from notify_wa import send_whatsapp; send_whatsapp("🖐️ "+msg)
        except: pass
        return {"ok":True,"msg":msg}
    except Exception as e: return {"ok":False,"msg":f"[{tag}] "+str(e)[:130]}

# ──────────────────────────── /performa (PINDAH dari publik ke admin -- private, 2-Jul) ────────────────────────────
# Angka backtest lengkap (return/DD/Calmar per-aset) skrg cuma keliatan admin, bukan publik.
PERFORMA=_PFHEAD+"<title>DNAYAKA · v20 Performa</title></head><body>"+_PFATMOS+r"""
<div class=wrap style="max-width:1000px;margin:0 auto;padding:24px 18px">
 <header style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:20px">
  <div style="font-family:var(--disp);font-weight:700;font-size:21px;color:var(--ink)">DNAYAKA <span style="color:var(--amber)">v20</span><span style="color:var(--dim);font-weight:400;font-size:12px;letter-spacing:.14em;margin-left:8px">PERFORMA STRATEGI · PRIVATE</span></div>
  <a href="/" style="color:var(--amber);text-decoration:none;font-size:11px;border:1px solid var(--line);padding:6px 11px;border-radius:4px">◂ ADMIN</a>
 </header>
 <div style="margin-bottom:14px;padding:11px 14px;border:1px solid var(--line);border-left:3px solid var(--amber);border-radius:6px;background:var(--panel);font-size:12px;color:var(--dim);line-height:1.6">
  <b style="color:var(--amber2)">Baca dulu:</b> angka di bawah = hasil <b>uji histori (backtest)</b> pada data asli, leverage 1×, fee dihitung. Ini <b>bukan profit yang dijamin</b>. Realistis ke depan jauh lebih kecil, dan <b>drawdown</b> (rugi sementara dari puncak) bisa lebih dalam dari closed-DD. Pakai modal yang siap hilang · bukan saran finansial.
 </div>
 <div class=symseg id=pfSeg style="margin-bottom:16px"><button data-s=BTCUSDT class=act>BTC</button><button data-s=ETHUSDT>ETH</button><button data-s=SOLUSDT>SOL</button></div>
 <div id=pfWarn style="display:none;margin-bottom:14px;padding:10px 14px;border:1px solid var(--down);border-radius:6px;background:rgba(255,69,58,.06);font-size:12px;color:var(--down)"></div>
 <div id=stats style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px"></div>
 <div class=panel style="padding:16px;margin-bottom:14px">
  <div class=panel-h><span class=t><span class=sq></span>SIMULATOR · Equity &amp; Leverage</span></div>
  <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-end;margin-top:8px">
   <div><label style="display:block;font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.1em;margin-bottom:5px">Modal awal ($)</label><input id=simCap type=number value=1000 min=1 style="background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);padding:8px 10px;width:130px"></div>
   <div><label style="display:block;font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.1em;margin-bottom:5px">Leverage</label><input id=simLev type=number value=1 min=1 max=20 step=0.5 style="background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);padding:8px 10px;width:90px"></div>
   <button onclick=runSim() style="padding:9px 18px;font-family:var(--mono);font-weight:600;letter-spacing:.08em;text-transform:uppercase;background:var(--amber);color:#160c00;border:0;border-radius:6px;cursor:pointer;font-size:12px">Hitung</button>
  </div>
  <div id=simOut style="margin-top:12px;font-size:12.5px;line-height:1.8;color:var(--dim)"></div>
 </div>
 <div class=panel style="padding:16px"><div class=panel-h><span class=t><span class=sq></span>EQUITY CURVE vs BUY&amp;HOLD · modal x1 (log scale)</span><span id=period style="font-size:10px;color:var(--dim)"></span></div><div style="display:flex;gap:14px;font-size:11px;margin:6px 0 0"><span><span style="color:#ff8c1a">■</span> Strategi v20</span><span><span style="color:#7a9cff">■</span> Buy &amp; Hold</span></div><div id=eq style="height:430px"></div></div>
 <div style="font-size:11px;color:var(--dim);line-height:1.6;margin-top:16px;border-top:1px solid var(--line);padding-top:12px">
  <b>Backtest</b> di data Binance ASLI (lev ≤1×, fee included). Hasil masa lalu BUKAN jaminan masa depan — forward jujur jauh lebih kecil. Bukan saran finansial.
 </div>
</div>
<script>
const $=id=>document.getElementById(id);
const fmtn=n=>Number(Math.round(n)).toLocaleString('en-US');
const PFHOST='http://localhost:8788';   // data v20 tetap dari server publik (endpoint read-only); halaman ini sendiri private :8789
const PFEP={BTCUSDT:PFHOST+'/api/btc_v20',ETHUSDT:PFHOST+'/api/eth_v20',SOLUSDT:PFHOST+'/api/sol_v20'};
const PFWARN={SOLUSDT:'⚠ SOL: hasil MARGINAL (Calmar rendah), belum direkomendasikan buat modal sungguhan — ditampilkan buat transparansi riset, bukan ajakan pakai.'};
let eqChart=null,eqS=null,holdS=null,curPerf=null;
function runSim(){
 if(!curPerf)return;const cap=Math.max(1,+$('simCap').value||1000),lev=Math.max(1,+$('simLev').value||1);
 const ret=curPerf.ret/100*lev, dd=Math.min(99,curPerf.maxdd*lev);   // aproksimasi linear: DD & ret scale ~leverage
 const finalCap=cap*(1+ret); const ruin=dd>=95;
 let h='Modal <b style="color:var(--ink)">$'+fmtn(cap)+'</b> · leverage <b style="color:var(--ink)">'+lev+'x</b> → estimasi akhir <b style="color:'+(ruin?'var(--down)':'var(--up)')+'">$'+fmtn(finalCap)+'</b> ('+(ret>=0?'+':'')+(ret*100).toFixed(0)+'%)<br>';
 h+='Estimasi max drawdown ter-leverage: <b style="color:var(--down)">-'+dd.toFixed(1)+'%</b>'+(ruin?' <b style="color:var(--down)">⚠ RISIKO LIKUIDASI TINGGI (DD≈100%)</b>':'');
 h+='<br><span style="font-size:10.5px;opacity:.75">Aproksimasi linear (return & DD closed-trade × leverage) — BUKAN simulasi ulang engine per-trade, dan mark-to-market real bisa lebih dalam dari closed-DD. Cuma buat gambaran kasar risiko.</span>';
 $('simOut').innerHTML=h;
}
function loadPf(sym){
 $('pfWarn').style.display=PFWARN[sym]?'block':'none'; if(PFWARN[sym])$('pfWarn').textContent=PFWARN[sym];
 fetch(PFEP[sym]).then(r=>r.json()).then(v=>{
  const p=v.perf||{},eq=v.equity||[],hold=v.hold||[];curPerf=p;runSim();
  const card=(l,val,col)=>'<div class=panel style="padding:13px 15px"><div class=label>'+l+'</div><div style="font-family:var(--mono);font-weight:600;font-size:23px;color:'+(col||'var(--ink)')+';margin-top:5px">'+val+'</div></div>';
  $('stats')['inner'+'HTML']=card('TOTAL RETURN','+'+fmtn(p.ret)+'%','var(--up)')+card('WIN RATE',p.wr+'%')+card('MAX DRAWDOWN','-'+p.maxdd+'%','var(--down)')+card('CALMAR',fmtn(p.cal))+card('TRADES',fmtn(p.n))+card('FINAL EQUITY','x'+(eq.length?eq[eq.length-1][1].toFixed(1):'-'),'var(--amber)')+card('BUY & HOLD',(p.hold_ret>=0?'+':'')+fmtn(p.hold_ret)+'%',p.hold_ret>=p.ret?'var(--up)':'var(--dim)');
  if(p.start){const d=t=>new Date(t*1000).toISOString().slice(0,10);$('period').textContent=d(p.start)+' → '+d(p.end);}
  if(!eqChart){eqChart=LightweightCharts.createChart($('eq'),{layout:{background:{color:'transparent'},textColor:'#8a7f63',fontFamily:'IBM Plex Mono',fontSize:11},grid:{vertLines:{color:'rgba(255,140,26,.03)'},horzLines:{color:'rgba(255,140,26,.03)'}},timeScale:{timeVisible:false,borderColor:'#1b1810'},rightPriceScale:{borderColor:'#1b1810',mode:1}});
   eqS=eqChart.addAreaSeries({lineColor:'#ff8c1a',topColor:'rgba(255,140,26,.30)',bottomColor:'rgba(255,140,26,.02)',lineWidth:2,priceLineVisible:false});
   holdS=eqChart.addLineSeries({color:'#7a9cff',lineWidth:1.5,priceLineVisible:false});
   const rs=()=>eqChart.applyOptions({width:$('eq').clientWidth,height:430});rs();new ResizeObserver(rs).observe($('eq'));}
  eqS.setData(eq.map(e=>({time:e[0],value:e[1]})));
  holdS.setData(hold.map(e=>({time:e[0],value:e[1]})));
  eqChart.timeScale().fitContent();
 });}
$('pfSeg').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('pfSeg').querySelectorAll('button').forEach(x=>x.classList.remove('act'));b.classList.add('act');loadPf(b.dataset.s);});
loadPf('BTCUSDT');
</script></body></html>"""

STOCKS=_PFHEAD+"<title>DNAYAKA · Saham IDX · PRIVATE</title></head><body>"+_PFATMOS+r"""
<div class=fnbar><span><b>F1</b> IHSG</span><span><b>F2</b> SINYAL</span><span><b>F3</b> WATCHLIST</span><span><b>F4</b> BANDARMOLOGY</span><span id=fnclock style="margin-left:auto;color:var(--amber)"></span></div>
<div class=wrap>
 <header class=hdr><div class=brand><span class=bt style="font-size:15px">▦</span> DNAYAKA<span style="color:var(--dim);font-weight:400;font-size:11px;letter-spacing:.18em;text-transform:uppercase;margin-left:9px">Saham IDX</span><span class=cur></span></div>
  <div class=r><button class=navtog aria-label=Menu onclick="this.nextElementSibling.classList.toggle('open')">☰</button><div class=navwrap><a class=navlink href="/">◂ ADMIN</a><span class=tag>SAHAM · PRIVATE</span></div></div></header>
 <section class=hero>
  <div class=label>IHSG · Jakarta Composite Index</div>
  <div class=bigprice id=ihsgpx>------</div>
  <div class="pxsub rv d1"><b id=ihsgchg>—</b> &nbsp;·&nbsp; REGIME <b id=ihsgreg>—</b> &nbsp;·&nbsp; <span id=ihsgbias class=aibias>—</span></div>
  <div class=gauges>
   <div class="gauge rv d2"><div class=g-l>RSI · 14</div><div class=g-v id=g_rsi>—</div></div>
   <div class="gauge rv d2"><div class=g-l>MACD hist</div><div class=g-v id=g_macd>—</div></div>
   <div class="gauge rv d3"><div class=g-l>vs SMA200</div><div class=g-v id=g_sma style="font-size:17px">—</div></div>
   <div class="gauge rv d3"><div class=g-l>52w Range</div><div class=g-v id=g_52 style="font-size:13px">—</div></div>
   <div class="gauge rv d4"><div class=g-l>Support / Resist</div><div class=g-v id=g_sr style="font-size:13px">—</div></div>
  </div>
 </section>
 <div class=grid>
  <section class="panel span2 rv d2">
   <div class=panel-h><span class=t><span class=sq></span><span id=chtitle>IHSG · Daily</span></span><div id=mfbox class=mfbox></div></div>
   <div id=schart style="height:320px;border-radius:4px;overflow:hidden"></div>
   <div class=rsi-l>RSI · 14</div><div id=srsi style="height:88px;border-radius:4px;overflow:hidden;border-top:1px solid var(--line)"></div>
   <div id=aibandar1 class=aibandar1 style="display:none"></div>
  </section>
  <section class="panel rv d3">
   <div class=panel-h><span class=t><span class=sq></span>Sinyal Hari Ini</span><span id=sigcount class=aibias>—</span></div>
   <div id=sigbanner></div><div id=buylist></div>
  </section>
  <section class="panel span2 rv d4">
   <div class=panel-h><span class=t><span class=sq></span><span id=watchh>Watchlist · ter-screen</span></span><span class=label>klik baris → chart</span></div>
   <div id=watchgrid class=watchgrid></div>
  </section>
  <section class="panel span2 rv d5">
   <div class=panel-h><span class=t><span class=sq></span>AI Bandarmology · Gemini</span><span class=aibias>money-flow read</span></div>
   <div id=bandaroverall class=aibody><div style="color:var(--dim);font-size:12px">memuat…</div></div>
   <p style="font-size:10px;color:var(--dim);margin-top:9px;line-height:1.5">⚠️ Pakai <b style="color:var(--amber)">ASING-NET (foreign flow IDX ASLI)</b> + inferensi money-flow. Kode broker per-saham (AK/BK/CC) = premium Stockbit; asing-net = gratis & lebih berguna.</p>
  </section>
  <section class="panel span2 rv d5">
   <div class=panel-h><span class=t><span class=sq></span>Foreign Flow · Asing (IDX, data ASLI)</span><span id=mktforeign class=aibias>—</span></div>
   <div class=ffgrid>
    <div><div class=ff-h style="color:var(--up)">▲ ASING BORONG (net beli, Rp M)</div><div id=fbuy class=ffcol></div></div>
    <div><div class=ff-h style="color:var(--down)">▼ ASING BUANG (net jual, Rp M)</div><div id=fsell class=ffcol></div></div>
   </div>
  </section>
  <section class="panel span2 rv d5">
   <div class=panel-h><span class=t><span class=sq></span>Top Broker Market-Wide · IDX</span><span id=idxdate class=aibias>—</span></div>
   <div id=topbrokers class=watchgrid></div>
   <p style="font-size:10px;color:var(--dim);margin-top:8px">Broker teraktif se-pasar (nilai transaksi hari bursa terakhir, data IDX). Bukan per-saham.</p>
  </section>
 </div>
 <footer class=foot><span>IDX Terminal · public</span><span>data: Yahoo via proxy · daily 2020→now</span><span id=ts>—</span></footer>
</div>
<script>
const $=id=>document.getElementById(id);const SF=n=>Number(n).toLocaleString('en-US');
let schart,sCandle,sVol,srsiChart,srsiS,curSym='^JKSE',sigData={};
function RSIc(c,p){p=p||14;let o=Array(c.length).fill(null),g=0,l=0;for(let i=1;i<=p;i++){const d=c[i]-c[i-1];if(d>=0)g+=d;else l-=d;}g/=p;l/=p;o[p]=100-100/(1+g/(l||1e-9));for(let i=p+1;i<c.length;i++){const d=c[i]-c[i-1];g=(g*(p-1)+(d>0?d:0))/p;l=(l*(p-1)+(d<0?-d:0))/p;o[i]=100-100/(1+g/(l||1e-9));}return o;}
function initS(){
 const base={layout:{background:{color:'transparent'},textColor:'#8a7f63',fontFamily:'IBM Plex Mono',fontSize:11},grid:{vertLines:{color:'rgba(255,140,26,.03)'},horzLines:{color:'rgba(255,140,26,.03)'}},timeScale:{borderColor:'#1b1810'},rightPriceScale:{borderColor:'#1b1810'},crosshair:{mode:0,vertLine:{color:'#ff8c1a66'},horzLine:{color:'#ff8c1a66'}}};
 schart=LightweightCharts.createChart($('schart'),base);
 sCandle=schart.addCandlestickSeries({upColor:'#27d07a',downColor:'#ff453a',borderVisible:false,wickUpColor:'#27d07a',wickDownColor:'#ff453a'});
 sVol=schart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'v'});sVol.priceScale().applyOptions({scaleMargins:{top:0.85,bottom:0}});
 srsiChart=LightweightCharts.createChart($('srsi'),Object.assign({},base,{timeScale:{visible:false,borderColor:'#1b1810'}}));
 srsiS=srsiChart.addLineSeries({color:'#ffb454',lineWidth:1.5,priceLineVisible:false});
 srsiS.createPriceLine({price:70,color:'rgba(255,69,58,.4)',lineStyle:2,lineWidth:1});srsiS.createPriceLine({price:30,color:'rgba(39,208,122,.4)',lineStyle:2,lineWidth:1});srsiS.createPriceLine({price:50,color:'rgba(138,127,99,.3)',lineStyle:3,lineWidth:1});
 schart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)srsiChart.timeScale().setVisibleLogicalRange(r);});
 srsiChart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)schart.timeScale().setVisibleLogicalRange(r);});
 loadChart('^JKSE','IHSG · Daily');
}
function loadChart(sym,title){curSym=sym;$('chtitle').textContent=title;
 document.querySelectorAll('.sigrow,.wrow').forEach(e=>e.classList.remove('sel'));
 fetch('http://localhost:8788/api/stock_klines?sym='+encodeURIComponent(sym)).then(r=>r.json()).then(d=>{
  sCandle.setData(d.map(k=>({time:k.time,open:k.open,high:k.high,low:k.low,close:k.close})));
  sVol.setData(d.map(k=>({time:k.time,value:k.volume,color:k.close>=k.open?'rgba(39,208,122,.3)':'rgba(255,69,58,.3)'})));
  const cl=d.map(k=>k.close);const r=RSIc(cl,14);srsiS.setData(d.map((k,i)=>r[i]!=null?{time:k.time,value:+r[i].toFixed(1)}:null).filter(Boolean));
  sCandle.setMarkers([]);   // IHSG & saham: NO marker buy/sell — strategi cuma BTC (per ticker+TF sendiri)
  schart.timeScale().fitContent();});
 showMF(sym);}
function showMF(sym){
 const all=[].concat(sigData.buys||[],sigData.watchlist||[]);const it=all.find(x=>x.sym===sym);
 if(!it){$('mfbox').innerHTML='';$('aibandar1').style.display='none';return;}
 const fc=it.flow=='akumulasi'?'acc':it.flow=='distribusi'?'dis':'neu';
 const smc=(it.sm||'').indexOf('AKUMULASI')>=0?'acc':(it.sm||'').indexOf('DISTRIBUSI')>=0?'dis':'neu';
 $('mfbox').innerHTML='<span class="mfi '+smc+'">'+(it.sm||'?')+'</span>'+
  '<span class="mfi '+fc+'">'+(it.flow||'').toUpperCase()+'</span>'+
  '<span>MFI <b>'+it.mfi+'</b></span><span>CMF <b>'+it.cmf+'</b></span>'+
  '<span>Buy '+it.buy_pct+'%/Sell '+it.sell_pct+'%</span>'+
  '<span class=bsbar><span class=bb style="flex:'+it.buy_pct+'"></span><span class=ss style="flex:'+it.sell_pct+'"></span></span>'+
  '<span style="color:var(--dim);font-size:10px">vol-besar akum/dist '+it.big_acc+'/'+it.big_dist+' · OBV '+it.obv_tr+'%</span>';
 const ab=(sigData.ai_bandar||{})[sym.replace('.JK','')];
 if(ab){$('aibandar1').style.display='block';$('aibandar1').innerHTML='<b style="color:var(--amber)">🤖 '+sym.replace('.JK','')+' · analisa mendalam:</b> '+ab+(it.diverg?'<br><span style="color:var(--dim);font-size:11px">⤷ '+it.diverg+'</span>':'');}else $('aibandar1').style.display='none';}
function loadIHSG(){fetch('http://localhost:8788/api/ihsg_ta').then(r=>r.json()).then(t=>{window._ihsg=t;
 $('ihsgpx').textContent=t.price?SF(t.price):'—';
 const c=$('ihsgchg');c.textContent=(t.change_pct>=0?'+':'')+t.change_pct+'%';c.className=t.change_pct>=0?'up':'down';
 $('ihsgreg').textContent=t.regime||'—';
 const b=t.bias||'NETRAL',cls=b=='BULLISH'?'bullish':b=='BEARISH'?'bearish':'netral';
 const ib=$('ihsgbias');ib.textContent=b;ib.className='aibias '+cls;
 $('g_rsi').textContent=t.rsi;$('g_macd').textContent=t.macd_hist;
 const gs=$('g_sma');gs.textContent=(t.dist_sma200_pct>=0?'+':'')+t.dist_sma200_pct+'%';gs.className='g-v '+(t.dist_sma200_pct>=0?'up':'down');
 $('g_52').textContent=SF(t.lo52)+'–'+SF(t.hi52);$('g_sr').textContent=SF(t.support)+' / '+SF(t.resistance);});}
function loadSig(){Promise.all([fetch('http://localhost:8788/api/stock_signal').then(r=>r.json()),fetch('http://localhost:8788/api/broksum').then(r=>r.json()).catch(_=>({}))]).then(([s,brk])=>{sigData=s;window._brk=brk;
 const t=window._ihsg||{},red=(t.bias=='BEARISH'),buys=s.buys||[];
 $('sigcount').textContent=buys.length+' beli · '+(s.n_watch||0)+' watch';
 let bn='';
 if(buys.length){bn=red
  ?`<div class=sigwarn>⚠️ IHSG MERAH (${t.regime||'lemah'}). ${buys.length} sinyal beli ini <b>LAWAN tren</b> — formula biasanya nahan. Kalau masuk: kecilkan size &amp; tunggu konfirmasi.</div>`
  :`<div class=sigok>✓ IHSG ${t.bias||''} — kondisi mendukung. ${buys.length} sinyal sesuai tren &amp; equity curve. Bagi modal ${s.default_K||4} slot, 1x.</div>`;}
 $('sigbanner').innerHTML=bn;
 $('buylist').innerHTML=buys.length?buys.map(b=>
  `<div class="sigrow ${red?'warn':'ok'}" onclick="loadChart('${b.sym}','${b.sym.replace('.JK','')} · Daily')"><span class=sym>${b.sym.replace('.JK','')}</span><span>@ ${SF(b.close)}</span><span style="color:var(--dim)">RSI ${b.rsi4}</span><span style="color:var(--dim)">${b.flow||''}</span></div>`).join('')
  :`<div class=nosig>⚪ Tidak ada sinyal beli hari ini${red?` — wajar, IHSG ${t.regime||'lemah'}: formula nahan cash (lindungi dari pisau jatuh).`:'.'}</div>`;
 const w=s.watchlist||[];
 $('watchh').textContent=`Watchlist · ${w.length} saham ter-screen (klik → chart · • = siap)`;
 $('watchgrid').innerHTML=w.length?w.map(x=>{const sy=x.sym.replace('.JK','');const smc=(x.sm||'').indexOf('AKUMULASI')>=0?'var(--up)':(x.sm||'').indexOf('DISTRIBUSI')>=0?'var(--down)':'var(--dim)';const ab=(sigData.ai_bandar||{})[sy]||'';const bk=((window._brk||{}).data||{})[sy];
  return `<div class="wrow${x.ready?' ready':''}" onclick="loadChart('${x.sym}','${sy} · Daily')"><span class=ws>${sy}${x.ready?' •':''} <span style="color:${smc};font-weight:600;font-size:11px">${(x.sm||'-').replace('SM ','▸ ')}</span>${x.foreign_net!=null?` <span style="font-size:10px;color:${x.foreign_net>=0?'var(--up)':'var(--down)'}">· asing ${x.foreign_net>=0?'+':''}${x.foreign_net}M</span>`:''}</span><span class=wm>RSI ${x.rsi4} · buy/sell ${x.buy_pct||'—'}/${x.sell_pct||'—'}% · vol-besar ${x.big_acc||0}↑/${x.big_dist||0}↓ · ${x.uptrend?'uptrend':'&lt;SMA200'}</span>${bk?`<span class=wb><b style="color:var(--up)">▸ beli:</b> ${(bk.top_buy||[]).map(x=>x.code).join(' ')||'-'} <b style="color:var(--down)">jual:</b> ${(bk.top_sell||[]).map(x=>x.code).join(' ')||'-'}</span>`:''}${ab?`<span class=wb><b>🤖 bandar:</b> ${ab}</span>`:''}</div>`;}).join('')
  :'<div style="color:var(--dim);font-size:12px">tidak ada.</div>';
 const ab=s.ai_bandar||{};
 $('bandaroverall').innerHTML=ab._overall?`<div class=cm>${ab._overall}</div>`:'<div style="color:var(--dim);font-size:12px">AI bandar off — set Gemini key di admin (jalankan signal_stocks.py --ai).</div>';
 const tb=s.top_brokers||[];$('idxdate').textContent=s.idx_date?('IDX '+s.idx_date):'—';
 $('topbrokers').innerHTML=tb.length?tb.map(b=>`<div class=wrow><span class=ws>${b.code} <span style="font-size:10px;color:var(--dim)">${b.val_b}M</span></span><span class=wm>${(b.name||'').slice(0,28)}</span><span class=wm>${b.freq} freq</span></div>`).join(''):'<div style="color:var(--dim);font-size:12px">jalankan idx_data.py (Proton off) → top broker muncul.</div>';
 const mfn=s.market_foreign_net,me=$('mktforeign');if(mfn!=null){me.textContent='Pasar net '+(mfn>=0?'+':'')+mfn+' M';me.className='aibias '+(mfn>=0?'bullish':'bearish');}
 $('fbuy').innerHTML=(s.top_fbuy||[]).map(x=>`<div class=fr><span class=s>${x.code}</span><b style="color:var(--up)">+${x.net}</b></div>`).join('')||'<div style="color:var(--dim);font-size:11px">— (idx_data Proton off)</div>';
 $('fsell').innerHTML=(s.top_fsell||[]).map(x=>`<div class=fr><span class=s>${x.code}</span><b style="color:var(--down)">${x.net}</b></div>`).join('')||'<div style="color:var(--dim);font-size:11px">—</div>';
 showMF(curSym);});}
function clock(){const d=new Date();$('fnclock').textContent=d.toUTCString().slice(17,25)+' UTC';$('ts').textContent=d.toUTCString().slice(5,22)+' UTC';}
initS();loadIHSG();loadSig();clock();
document.querySelectorAll('.panel').forEach(p=>{const h=p.querySelector('.panel-h');if(!h||h.querySelector('.mini'))return;const m=document.createElement('span');m.className='mini';m.textContent='–';m.title='minimize / maximize';m.onclick=e=>{e.stopPropagation();p.classList.toggle('collapsed');m.textContent=p.classList.contains('collapsed')?'+':'–';};h.appendChild(m);});
setInterval(clock,1000);setInterval(loadIHSG,60000);setInterval(loadSig,60000);
</script></body></html>"""

PAGE=r"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>DNAYAKA · Admin</title>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@400..800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel=stylesheet>
<style>:root{--bg:#000;--panel:#070707;--ink:#e8e2d0;--dim:#8a7f63;--amber:#ff8c1a;--up:#27d07a;--down:#ff453a;--line:#1b1810;--mono:'IBM Plex Mono',monospace;--disp:'Bricolage Grotesque',sans-serif}
*{margin:0;padding:0;box-sizing:border-box}body{background:var(--bg);color:var(--ink);font-family:var(--mono);font-size:13px;max-width:520px;margin:0 auto;padding:18px}
.hd{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:16px}
.hd .b{font-family:var(--disp);font-weight:700;font-size:16px}.hd .b span{color:var(--down)}
a.back{color:var(--amber);text-decoration:none;font-size:11px;border:1px solid var(--line);padding:5px 10px;border-radius:4px}
.state{padding:4px 10px;border:1px solid var(--line);border-radius:3px;font-weight:600;font-size:11px;letter-spacing:.1em}
.state.live{color:var(--down);border-color:rgba(255,69,58,.5);box-shadow:0 0 14px rgba(255,69,58,.25)}.state.paper{color:var(--up)}.state.test{color:var(--amber);border-color:rgba(255,140,26,.5)}
.netsw input:checked+.sl{background:rgba(255,69,58,.25);border-color:var(--down)}.netsw input:checked+.sl:before{transform:translateX(26px);background:var(--down);box-shadow:0 0 11px var(--down)}
.netsw .sl{background:rgba(39,208,122,.18);border-color:var(--up)}.netsw .sl:before{background:var(--up)}
.px{font-family:var(--mono);font-weight:600;font-size:40px;font-variant-numeric:tabular-nums;margin:10px 0 18px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:15px;margin-bottom:13px}
.panel h3{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--amber);margin-bottom:12px}
.switch{display:flex;align-items:center;justify-content:space-between;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:13px 15px;margin-bottom:8px}
.switch b{font-family:var(--disp);font-size:15px}
.phys{position:relative;width:56px;height:30px}.phys input{opacity:0;width:0;height:0}
.sl{position:absolute;inset:0;background:#15130c;border:1px solid var(--dim);border-radius:30px;cursor:pointer;transition:.3s}
.sl:before{content:"";position:absolute;width:22px;height:22px;left:3px;top:3px;background:var(--dim);border-radius:50%;transition:.3s}
.phys input:checked+.sl{background:rgba(255,69,58,.25);border-color:var(--down)}.phys input:checked+.sl:before{transform:translateX(26px);background:var(--down);box-shadow:0 0 11px var(--down)}
.warn{font-size:11px;color:var(--amber);margin:4px 0}
.field{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}label{display:block;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin-bottom:5px}
input.inp{width:100%;background:var(--bg);border:1px solid var(--line);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:15px;padding:11px}input.inp:focus{outline:0;border-color:var(--amber)}
.btn{width:100%;padding:13px;font-family:var(--mono);font-weight:600;letter-spacing:.1em;text-transform:uppercase;background:var(--amber);color:#160c00;border:0;border-radius:6px;cursor:pointer;margin-top:12px;font-size:12px}.btn.ghost{background:transparent;color:var(--amber);border:1px solid var(--amber)}
.tbig{display:grid;grid-template-columns:1fr 1fr;gap:11px}.tbtn{padding:26px;border:1px solid;border-radius:9px;font-family:var(--disp);font-weight:700;font-size:20px;background:transparent;cursor:pointer;text-transform:uppercase}
.tbtn.buy{color:var(--up);border-color:rgba(39,208,122,.4)}.tbtn.buy:hover{background:rgba(39,208,122,.12)}.tbtn.sell{color:var(--down);border-color:rgba(255,69,58,.4)}.tbtn.sell:hover{background:rgba(255,69,58,.12)}
.tbtn .s{display:block;font-family:var(--mono);font-size:10px;opacity:.7;margin-top:6px}
.saved{text-align:center;font-size:11px;color:var(--up);height:14px;margin-top:7px}.keystat{font-size:12px;margin-bottom:6px}
.pos{display:flex;justify-content:space-between;padding:11px 13px;background:var(--bg);border:1px solid var(--line);border-radius:5px;font-size:13px}.flat{color:var(--dim)}.long{color:var(--up)}.short{color:var(--down)}

.toast{position:fixed;top:16px;right:16px;z-index:300;display:flex;flex-direction:column;gap:8px}
.toast .t{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--amber);border-radius:7px;padding:12px 15px;font-size:13px;min-width:210px;box-shadow:0 12px 36px rgba(0,0,0,.75);animation:tin .3s cubic-bezier(.2,.8,.2,1);display:flex;align-items:center;gap:9px}
.toast .t.ok{border-left-color:var(--up)}.toast .t.err{border-left-color:var(--down)}
.toast .ic{font-size:15px;color:var(--amber)}.toast .t.ok .ic{color:var(--up)}.toast .t.err .ic{color:var(--down)}
@keyframes tin{from{opacity:0;transform:translateX(28px)}to{opacity:1;transform:none}}
.toast .t.out{animation:tout .3s forwards}@keyframes tout{to{opacity:0;transform:translateX(28px)}}
.modal{position:fixed;inset:0;z-index:400;background:rgba(0,0,0,.72);backdrop-filter:blur(5px);display:none;align-items:center;justify-content:center;padding:20px}
.modal.show{display:flex;animation:tin .2s}
.modal .box{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:24px;max-width:330px;width:100%;text-align:center;box-shadow:0 30px 80px rgba(0,0,0,.8)}
.modal h4{font-family:var(--disp);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin-bottom:10px}
.modal .big{font-family:var(--disp);font-size:27px;font-weight:700;margin:4px 0 8px}
.modal p{font-size:12px;color:var(--dim);margin-bottom:20px;line-height:1.5}
.modal .row{display:flex;gap:10px}
.modal .row button{flex:1;padding:13px;border-radius:8px;font-family:var(--mono);font-weight:600;cursor:pointer;border:0;font-size:13px;transition:filter .15s}
.modal .row button:hover{filter:brightness(1.12)}
.modal .cancel{background:transparent;color:var(--dim);border:1px solid var(--line)}
.modal .ok{color:#0a0700}.modal .ok.buy{background:var(--up)}.modal .ok.sell{background:var(--down);color:#fff}
</style></head><body>
<div class=hd><div class=b>DNAYAKA<span>·</span>ADMIN</div><div style="display:flex;gap:8px;align-items:center"><span class="state paper" id=state>PAPER</span><a class=back href="/performa">performa</a><a class=back href="/saham">saham</a><a class=back href="http://localhost:8788" target=_blank>terminal ↗</a></div></div>
<div class=px id=px>$—</div>
<div class=panel><h3>System · BTC v20</h3>
 <div class=switch><b id=livelbl>PAPER · safe</b><label class=phys><input type=checkbox id=live><span class=sl></span></label></div>
 <div class=switch><b id=netlbl>TESTNET · sandbox</b><label class="phys netsw"><input type=checkbox id=net><span class=sl></span></label></div>
 <p class=warn id=modewarn>PAPER = nol order. LIVE+TESTNET = order palsu (aman tes). LIVE+MAINNET = UANG ASLI.</p>
 <div class=field><div><label>Size USD</label><input class=inp type=number id=size></div><div><label>Leverage (max 1x)</label><input class=inp type=number id=lev min=1 max=1 value=1 title="Dikunci 1x (riset: WAJIB <=1x)"></div></div>
 <div class=switch><b id=walbl>WhatsApp · OFF</b><label class=phys><input type=checkbox id=wa><span class=sl></span></label></div>
 <p class=warn>Notifikasi WhatsApp (sinyal/breaker). OFF = bot diam. Bisa dinyalakan kapan saja di sini.</p>
 <p class=warn id=not></p><button class=btn onclick=saveCfg()>Commit</button><div class=saved id=cs></div>
</div>
<div class=panel><h3>Fed Live · Video (manual)</h3>
 <div class=field><div><label>URL/ID YouTube (video yg BENERAN lagi live)</label><input class=inp id=fedvid placeholder="https://youtube.com/watch?v=... atau video-id"></div><div><label>Label (opsional)</label><input class=inp id=fedlabel placeholder="mis. FOMC Press Conference"></div></div>
 <button class=btn onclick=saveFedLive()>Simpan</button> <button class="btn ghost" onclick="$('fedvid').value='';$('fedlabel').value='';saveFedLive()">Kosongkan (matikan panel publik)</button><div class=saved id=fedmsg></div>
 <p class=warn>Kalau kosong, panel "Fed Live" di terminal publik SEMBUNYI. Isi pas ada siaran nyata (mis. dari federalreserve.gov/live-broadcast atau YouTube Fed) biar publik bisa nonton + auto-translate CC.</p>
</div>
<div class=panel><h3>Users · Akses Terminal Publik</h3>
 <div id=ulist style="font-size:12px;margin-bottom:10px">—</div>
 <div class=field><div><label>Username</label><input class=inp id=uu placeholder="username"></div><div><label>Password</label><input class=inp id=upw type=password placeholder="password"></div></div>
 <div class=field><div><label>Trial hari (0 = permanen)</label><input class=inp type=number id=udays value=0 min=0></div><div style="display:flex;align-items:flex-end;gap:8px"><label style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--dim)"><input type=checkbox id=uadm> admin</label></div></div>
 <button class="btn ghost" onclick=addUser()>+ Buat User</button><div class=saved id=umsg></div>
 <p class=warn>Signup HANYA di sini. Trial habis -> login otomatis ditolak & session mati.</p>
</div>
<div class=panel><h3>Manual Execute</h3>
 <div class=tbig><button class="tbtn buy" onclick="trade('buy')">▲ Long<span class=s>Market Buy</span></button><button class="tbtn sell" onclick="trade('sell')">▼ Short<span class=s>Market Sell</span></button></div>
 <div class=saved id=tmsg style="color:var(--dim);font-size:12px;margin-top:12px">size dari config di atas</div>
</div>
<div class=panel><h3>Position</h3><div id=pos></div><div id=twbox></div></div>
<div class=panel><h3>AI · Gemini (second opinion)</h3>
 <div class=keystat id=gks>—</div>
 <button class="btn ghost" onclick=secop() id=sobtn>🤖 Minta Second Opinion</button>
 <div id=sotext style="font-size:12px;line-height:1.6;color:var(--ink);margin-top:10px;min-height:14px"></div>
 <p class=warn style="margin-top:8px">Analisa AI · BUKAN saran trade.</p>
 <label style=margin-top:6px>Gemini API Key</label><input class=inp id=gk type=password placeholder="paste Gemini key (AI Studio)">
 <button class="btn ghost" onclick=saveGemini()>🔒 Store Gemini Key</button><div class=saved id=gsv></div>
</div>
<div class=panel><h3>Saham IDX · Sinyal & AI Bandar</h3>
 <button class="btn ghost" onclick=refreshStocks()>🔄 Perbarui Sinyal + AI Bandar</button>
 <div class=saved id=stmsg style="color:var(--dim);font-size:11px;margin-top:8px">fetch data terbaru + hitung sinyal + money-flow + AI bandar (1 batch). ~5-10 menit.</div>
 <a class=back href="http://localhost:8788/saham" target=_blank style="display:inline-block;margin-top:10px">buka terminal saham ↗</a>
</div>
<div class=panel><h3>API Credentials</h3><div class=keystat id=ks>—</div>
 <label>Key</label><input class=inp id=k placeholder="paste key"><label style=margin-top:9px>Secret</label><input class=inp id=s type=password placeholder="paste secret">
 <p class=warn>Futures · IP-restrict · NO withdraw · lokal chmod600</p><button class="btn ghost" onclick=saveKeys()>🔒 Store</button><div class=saved id=ksv></div>
</div>
<div class=toast id=toast></div><div class=modal id=modal><div class=box><h4>Konfirmasi Market Order</h4><div class=big id=mbig></div><p id=modalwarn>Akan dieksekusi di Binance futures.</p><div class=row><button class=cancel onclick=closeM()>Batal</button><button class=ok id=mok>Confirm</button></div></div></div><script>const $=id=>document.getElementById(id);
function fp(n){const d=n<100?2:0;return '$'+Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d})}
function px(){fetch('/api/metrics').then(r=>r.json()).then(m=>$('px').textContent=fp(m.mark))}
function cfg(){fetch('/api/config').then(r=>r.json()).then(c=>{$('live').checked=c.live;$('net').checked=(c.net=='mainnet');$('size').value=c.size_usd;$('lev').value=c.leverage;$('wa').checked=!!c.wa_enabled;waL();lv();nt();keyst()})}
function loadFedLive(){fetch('/api/fedlive').then(r=>r.json()).then(d=>{$('fedvid').value=d.video_id||'';$('fedlabel').value=d.label||''})}
function saveFedLive(){fetch('/api/fedlive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({video:$('fedvid').value.trim(),label:$('fedlabel').value.trim()})}).then(r=>r.json()).then(d=>{if(d.ok){$('fedvid').value=d.video_id||'';$('fedmsg').textContent='✓ tersimpan';$('fedmsg').style.color='var(--up)';toast(d.video_id?'Fed Live diset: '+d.video_id:'Fed Live dikosongkan (panel publik sembunyi)','ok');}else{$('fedmsg').textContent=d.msg||'gagal';$('fedmsg').style.color='var(--down)';toast(d.msg||'gagal','err');}setTimeout(()=>$('fedmsg').textContent='',2500)})}
function waL(){const on=$('wa').checked;$('walbl').textContent='WhatsApp · '+(on?'ON':'OFF');$('walbl').style.color=on?'var(--up)':'var(--dim)'}
function lv(){const live=$('live').checked,main=$('net').checked;
 $('netlbl').textContent=main?'MAINNET · uang ASLI':'TESTNET · sandbox';
 let txt,cls;if(!live){txt='PAPER';cls='paper'}else if(main){txt='● LIVE·REAL';cls='live'}else{txt='● LIVE·TEST';cls='test'}
 $('state').textContent=txt;$('state').className='state '+cls;
 $('livelbl').textContent=live?(main?'LIVE · UANG ASLI':'LIVE · testnet (palsu)'):'PAPER · safe'}
function nt(){const n=(+$('size').value)*(+$('lev').value);$('not').textContent='Notional ~$'+n+(n<100?' · ⚠ < min $100':' · ✓')}
$('live').onchange=lv;$('net').onchange=()=>{lv();keyst()};$('size').oninput=nt;$('lev').oninput=nt;
function saveCfg(){const main=$('net').checked;if($('live').checked&&main&&!confirm('LIVE + MAINNET = UANG ASLI. Lanjut?'))return;fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({live:$('live').checked,net:main?'mainnet':'testnet',size_usd:+$('size').value,leverage:+$('lev').value,wa_enabled:$('wa').checked})}).then(r=>r.json()).then(_=>{$('cs').textContent='✓ committed';toast('Config tersimpan ('+(main?'MAINNET':'TESTNET')+')','ok');setTimeout(()=>$('cs').textContent='',2000)})}
function keyst(){fetch('/api/secrets').then(r=>r.json()).then(d=>{const main=$('net').checked,o=main?d.mainnet:d.testnet,nm=main?'MAINNET':'TESTNET';$('ks').innerHTML=o&&o.set?'<span style=color:var(--up)>● '+nm+' key active ('+o.masked+')</span>':'<span style=color:var(--down)>○ no '+nm+' key</span>';$('gks').innerHTML=d.gemini?'<span style=color:var(--up)>● Gemini key active</span>':'<span style=color:var(--down)>○ no Gemini key</span>'})}
function saveGemini(){const g=$('gk').value;if(!g){alert('isi');return}fetch('/api/secrets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({gemini:g})}).then(r=>r.json()).then(_=>{$('gk').value='';$('gsv').textContent='✓ stored';toast('Gemini key tersimpan','ok');setTimeout(()=>$('gsv').textContent='',2000);keyst()})}
function secop(){$('sobtn').disabled=true;$('sotext').textContent='⟳ Gemini berpikir…';$('sotext').style.color='var(--amber)';fetch('/api/secondopinion').then(r=>r.json()).then(d=>{$('sotext').style.color=d.ok?'var(--ink)':'var(--down)';$('sotext').textContent=d.text;$('sobtn').disabled=false}).catch(_=>{$('sotext').textContent='gagal';$('sobtn').disabled=false})}
function saveKeys(){const k=$('k').value,s=$('s').value;if(!k||!s){alert('isi');return}const main=$('net').checked;fetch('/api/secrets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:k,secret:s,net:main?'mainnet':'testnet'})}).then(r=>r.json()).then(_=>{$('k').value='';$('s').value='';$('ksv').textContent='✓ stored '+(main?'MAINNET':'TESTNET');toast('API key '+(main?'MAINNET':'TESTNET')+' tersimpan','ok');setTimeout(()=>$('ksv').textContent='',2000);keyst()})}
let pend=null,tradeBusy=false;
function toast(m,t){const e=document.createElement('div');e.className='t '+(t||'');e.innerHTML='<span class=ic>'+(t=='ok'?'✓':t=='err'?'✕':'•')+'</span>'+m;$('toast').appendChild(e);setTimeout(()=>{e.classList.add('out');setTimeout(()=>e.remove(),300)},3800)}
function trade(side){if(tradeBusy)return;const sz=$('size').value,main=$('net').checked;pend=side;$('mbig').innerHTML='<span style="color:'+(side=='buy'?'var(--up)':'var(--down)')+'">'+(side=='buy'?'▲ LONG':'▼ SHORT')+' ~$'+sz+'</span>';$('modalwarn').innerHTML=main?'⚠️ <b style=color:var(--down)>UANG ASLI</b> di Binance MAINNET.':'TESTNET (uang palsu) — aman buat tes.';$('mok').className='ok '+side;$('mok').textContent='Confirm '+(side=='buy'?'LONG':'SHORT');$('modal').classList.add('show')}
function closeM(){$('modal').classList.remove('show');pend=null}
function doTrade(){if(tradeBusy)return;const side=pend;closeM();if(!side)return;tradeBusy=true;$('tmsg').textContent='⟳ sending…';$('tmsg').style.color='var(--amber)';toast('Order '+side.toUpperCase()+' dikirim…','');fetch('/api/trade',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({side})}).then(r=>r.json()).then(d=>{$('tmsg').textContent=d.msg;$('tmsg').style.color=d.ok?'var(--up)':'var(--down)';toast(d.msg,d.ok?'ok':'err');tradeBusy=false;setTimeout(pos,1500)}).catch(_=>{tradeBusy=false})}
function pos(){fetch('/api/status').then(r=>r.json()).then(d=>{const s=d.sleeves.v20||{};const c=s.pos>0?'long':s.pos<0?'short':'flat';const t=s.pos>0?'LONG':s.pos<0?'SHORT':'FLAT';$('pos').innerHTML='<div class=pos><span class=nm>v20 <b class='+c+'>'+t+'</b>'+(s.pos?' @'+Math.round(s.entry):'')+'</span><span style=color:var(--dim)>×'+(s.equity||1).toFixed(3)+' · '+(s.ntr||0)+'t</span></div>';
 const br=d.breaker||{},tw=d.tripwire||{tier:0,reasons:[]};
 let html='';
 if(br.halted) html+='<div style="margin-top:6px;padding:6px 8px;border-radius:6px;background:rgba(255,80,80,.12);color:var(--down);font-size:11px">🛑 HALTED — '+esc(br.reason||'?')+' — resume manual via bot_v22.py --resume</div>';
 else if(tw.tier>=2) html+='<div style="margin-top:6px;padding:6px 8px;border-radius:6px;background:rgba(255,80,80,.12);color:var(--down);font-size:11px">🛑 tripwire tier2 (paper, belum halt): '+esc((tw.reasons||[]).join(' ; '))+'</div>';
 else if(tw.tier==1) html+='<div style="margin-top:6px;padding:6px 8px;border-radius:6px;background:rgba(255,180,50,.12);color:var(--amber);font-size:11px">⚠️ tripwire tier1 — size ×'+(tw.size_mult||.5)+': '+esc((tw.reasons||[]).join(' ; '))+'</div>';
 $('twbox').innerHTML=html})}
function refreshStocks(){$('stmsg').textContent='⟳ menjalankan…';$('stmsg').style.color='var(--amber)';toast('Refresh saham dimulai…','');fetch('/api/refresh_stocks',{method:'POST',headers:{'Content-Type':'application/json'}}).then(r=>r.json()).then(d=>{$('stmsg').textContent=d.msg;$('stmsg').style.color=d.ok?'var(--up)':'var(--down)';toast(d.ok?'Refresh saham jalan':'gagal',d.ok?'ok':'err')}).catch(_=>{$('stmsg').textContent='gagal';})}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function loadUsers(){fetch('/api/users').then(r=>r.json()).then(d=>{const us=d.users||[];if(!us.length){$('ulist').textContent='belum ada user';return}
 const H=us.map(u=>{const nm=esc(u.u);const tag=u.admin?'<span style=color:var(--amber)>admin</span>':(u.trial?(u.expired?'<span style=color:var(--down)>trial habis</span>':'<span style=color:var(--up)>trial '+u.days_left+'h</span>'):'<span style=color:var(--dim)>permanen</span>');
  const del='<button onclick="delUser(\''+nm+'\')" style="background:none;border:1px solid var(--line);color:var(--down);border-radius:4px;cursor:pointer;font-size:10px;padding:2px 7px">hapus</button>';
  return '<div style="display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--line)"><span><b>'+nm+'</b> · '+tag+'</span>'+del+'</div>'}).join('');
 $('ulist')['inner'+'HTML']=H})}
function addUser(){const u=$('uu').value.trim(),p=$('upw').value,days=+$('udays').value||0;if(!u||!p){toast('isi username & password','err');return}
 fetch('/api/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({act:'add',user:u,pw:p,admin:$('uadm').checked,days:days})}).then(r=>r.json()).then(d=>{if(d.ok){$('uu').value='';$('upw').value='';$('udays').value=0;$('uadm').checked=false;toast('User '+u+' dibuat'+(days>0?' (trial '+days+'h)':''),'ok');loadUsers()}else toast(d.msg||'gagal','err')})}
function delUser(u){if(!confirm('Hapus user '+u+'?'))return;fetch('/api/users',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({act:'del',user:u})}).then(r=>r.json()).then(d=>{if(d.ok){toast('User '+u+' dihapus','ok');loadUsers()}else toast(d.msg||'gagal','err')})}
$('wa').addEventListener('change',waL);
$('mok').onclick=doTrade;px();cfg();keyst();pos();loadUsers();loadFedLive();setInterval(px,15000);setInterval(pos,10000)
</script></body></html>"""
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _s(self,c,ct,b): self.send_response(c);self.send_header("Content-Type",ct);self.end_headers();self.wfile.write(b if isinstance(b,bytes) else b.encode())
    def _local_ok(self):   # localhost WAJIB: client IP + Host header dua-duanya lokal (bind 127.0.0.1 + anti DNS-rebind)
        return self.client_address[0] in ("127.0.0.1","::1") and self.headers.get("Host","").split(":")[0] in ("127.0.0.1","localhost","")
    def do_GET(self):
        if not self._local_ok(): return self._s(403,"text/plain","forbidden")
        path=urlparse(self.path).path
        if path=="/": return self._s(200,"text/html",PAGE)
        if path=="/performa": return self._s(200,"text/html",PERFORMA)   # PINDAH dari publik -- private, 2-Jul
        if path=="/saham": return self._s(200,"text/html",STOCKS)        # PINDAH dari publik -- private, 2-Jul
        if path=="/api/config": return self._s(200,"application/json",json.dumps(load()))
        if path=="/api/fedlive": return self._s(200,"application/json",json.dumps(load_fedlive()))
        if path=="/api/metrics":
            d={"mark":0}
            try: d["mark"]=float(S.get(FAPI+"/fapi/v1/premiumIndex?symbol=BTCUSDT",timeout=8,verify=False).json()["markPrice"])
            except: pass
            return self._s(200,"application/json",json.dumps(d))
        if path=="/api/status":
            d={"sleeves":{},"breaker":{},"tripwire":{}}
            try:
                st=json.load(open(STATE))
                v=st.get("v20",{}); d["sleeves"]["v20"]={k:x for k,x in v.items() if k not in("hist","equity_hist")}
                d["breaker"]=st.get("breaker",{})
                d["tripwire"]=st.get("tripwire",{"tier":0,"reasons":[],"size_mult":1.0})
            except: pass
            return self._s(200,"application/json",json.dumps(d))
        if path=="/api/secrets":
            def st(net):
                k,_=load_keys(net); return {"set":bool(k),"masked":(k[:4]+"…"+k[-4:]) if len(k)>8 else ""}
            return self._s(200,"application/json",json.dumps({"testnet":st("testnet"),"mainnet":st("mainnet"),"gemini":bool(gemini_key())}))
        if path=="/api/secondopinion":
            return self._s(200,"application/json",json.dumps(second_opinion()))
        if path=="/api/users":
            return self._s(200,"application/json",json.dumps({"users":list_users()}))
        self._s(404,"text/plain","")
    def do_POST(self):
        if not self._local_ok(): return self._s(403,"text/plain","forbidden")              # S3 anti DNS-rebind
        if "application/json" not in self.headers.get("Content-Type",""):                   # S3 tolak simple-CORS text/plain
            return self._s(415,"application/json",'{"ok":false,"msg":"json only"}')
        try:
            n=max(0,min(int(self.headers.get("Content-Length",0)),65536)); body=json.loads(self.rfile.read(n).decode()) if n else {}
        except Exception: return self._s(400,"application/json",'{"ok":false,"msg":"bad body"}')
        if self.path=="/api/config":
            c=load()
            if "live" in body: c["live"]=bool(body["live"])
            if "net" in body: c["net"]="mainnet" if body["net"] in (True,"mainnet") else "testnet"
            if "wa_enabled" in body: c["wa_enabled"]=bool(body["wa_enabled"])   # toggle fitur WhatsApp
            c["size_usd"]=max(1,min(c.get("max_size_usd",2000),int(body.get("size_usd",c["size_usd"]))))
            c["leverage"]=max(1,min(1,int(body.get("leverage",c["leverage"]))))   # HARD cap 1x (riset: WAJIB <=1x)
            save(c); return self._s(200,"application/json",'{"ok":true}')
        if self.path=="/api/fedlive":   # manual: admin tempel link/ID video YouTube Fed yg BENERAN lagi live (bukan auto-tebak channel)
            vid=_yt_video_id(body.get("video",""))
            if body.get("video","").strip() and not vid:
                return self._s(200,"application/json",'{"ok":false,"msg":"URL/ID YouTube tidak dikenali"}')
            d=save_fedlive(vid, (body.get("label") or "").strip()[:80])
            return self._s(200,"application/json",json.dumps({"ok":True,**d}))
        if self.path=="/api/users":   # kelola akun terminal publik (admin lokal saja)
            act=body.get("act"); un=(body.get("user") or "").strip()
            if act=="add" and un and body.get("pw"):
                add_user(un,body["pw"],bool(body.get("admin")),int(body.get("days",0) or 0)); return self._s(200,"application/json",'{"ok":true}')
            if act=="expiry" and un: set_expiry(un,int(body.get("days",0) or 0)); return self._s(200,"application/json",'{"ok":true}')
            if act=="del" and un:
                us=load_users()
                if un in us and us[un].get("admin") and sum(1 for v in us.values() if v.get("admin"))<=1:
                    return self._s(200,"application/json",'{"ok":false,"msg":"tak bisa hapus admin terakhir"}')
                del_user(un); return self._s(200,"application/json",'{"ok":true}')
            return self._s(400,"application/json",'{"ok":false,"msg":"bad"}')
        if self.path=="/api/secrets":
            try: cur=json.load(open(SEC))
            except: cur={}
            if not isinstance(cur,dict): cur={}
            if "key" in cur and "mainnet" not in cur:                       # migrasi format lama -> mainnet
                cur={"mainnet":{"key":cur.get("key",""),"secret":cur.get("secret","")},"gemini":cur.get("gemini","")}
            if "gemini" in body:                                            # simpan key Gemini (AI)
                cur["gemini"]=body.get("gemini","")
            else:
                net="mainnet" if body.get("net") in (True,"mainnet") else "testnet"
                cur[net]={"key":body.get("key",""),"secret":body.get("secret","")}  # set net ini, lain dipertahankan
            fd=os.open(SEC+".tmp", os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)   # S6: atomik + 600 dari awal (no world-readable window)
            with os.fdopen(fd,"w") as f: json.dump(cur,f)
            os.replace(SEC+".tmp", SEC)
            return self._s(200,"application/json",'{"ok":true}')
        if self.path=="/api/trade":
            if not _TRADE_LK.acquire(blocking=False):                          # M4: anti double-submit (serialize)
                return self._s(200,"application/json",'{"ok":false,"msg":"order lain sedang diproses"}')
            try: return self._s(200,"application/json",json.dumps(place_market(body.get("side","buy"))))
            finally: _TRADE_LK.release()
        if self.path=="/api/refresh_stocks":
            import subprocess
            if _JOB["stocks"]:                                                 # S4: single-flight (cegah 2 writer korup file)
                return self._s(200,"application/json",'{"ok":false,"msg":"refresh masih jalan, tunggu."}')
            try:
                _JOB["stocks"]=True
                p=subprocess.Popen(["python3","signal_stocks.py","--update","--ai"], cwd=HERE+"/stocks",
                                 stdout=open(HERE+"/stocks/signal.log","a"), stderr=subprocess.STDOUT)
                threading.Thread(target=lambda:(p.wait(), _JOB.__setitem__("stocks",False)), daemon=True).start()
                return self._s(200,"application/json",'{"ok":true,"msg":"Refresh saham jalan di background (~5-10 mnt: fetch + sinyal + AI bandar). Refresh terminal saham nanti."}')
            except Exception as e:
                _JOB["stocks"]=False
                return self._s(200,"application/json",json.dumps({"ok":False,"msg":str(e)[:120]}))
        self._s(404,"text/plain","")
if __name__=="__main__":
    print("PRIVATE admin http://127.0.0.1:8789 (localhost only)")
    ThreadingHTTPServer(("127.0.0.1",8789),H).serve_forever()
