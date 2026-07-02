#!/usr/bin/env python3
"""gen_demo.py — builds the static GitHub-Pages preview in docs/ (index.html + journal.html).

No backend, no fetch() calls: real historical BTC bars + real v20 trades (frozen snapshot from
btc_v20.json) are embedded directly as JSON in the HTML, plus a small set of clearly-synthetic
demo journal entries. Reuses the exact CSS from config_server.py so the preview matches the real
app pixel-for-pixel. Re-run this after `python3 btc15m.py` if you want to refresh the snapshot.

  python3 docs/gen_demo.py
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_server import HEAD, ATMOS   # reuse verbatim (CSS + favicon + fonts) -- never drift from the real app

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO_URL = "https://github.com/dnayaka/btc-crypto-terminal"

BANNER_CSS = """
.demoban{position:sticky;top:0;z-index:80;background:linear-gradient(90deg,#1a0f00,#0a0700);border-bottom:1px solid var(--amber);
 padding:9px 16px;font-size:11.5px;color:var(--ink);display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap;text-align:center}
.demoban b{color:var(--amber)}
.demoban a{color:var(--amber2);text-decoration:none;border-bottom:1px dashed var(--amber2)}
.demoban a:hover{color:var(--amber)}
"""

def banner(active):
    return (f'<div class=demoban>&#128274; <b>Static preview</b> - real historical data baked in, zero backend, zero live connection. '
            f'Clone the repo and run <code>./setup.sh</code> for the real thing with your own account. '
            f'<a href="{REPO_URL}" target=_blank rel="noopener noreferrer">view on GitHub &#8599;</a></div>')


def build_terminal():
    with open(os.path.join(ROOT, "btc_v20.json")) as f:
        d = json.load(f)
    bars = d["bars"][-3000:]
    t0, t1 = bars[0]["time"], bars[-1]["time"]
    trades = [t for t in d["trades"] if t0 <= t["et"] <= t1]
    perf = d["perf"]
    last_close = bars[-1]["close"]
    prev_close = bars[0]["close"]
    chg = (last_close / prev_close - 1) * 100

    bars_json = json.dumps(bars)
    trades_json = json.dumps(trades)

    html = HEAD + "<style>" + BANNER_CSS + """
.demo-hero{padding:26px 0 18px}
</style><title>DNAYAKA - Crypto Terminal (static preview)</title></head><body>""" + ATMOS + banner("terminal") + f"""
<div class=wrap>
 <header class=hdr><div class=brand><span class=bt>&#8383;</span> DNAYAKA<span style="color:var(--dim);font-weight:400;font-size:11px;letter-spacing:.18em;text-transform:uppercase;margin-left:9px">Crypto Terminal</span><span class=cur></span></div>
  <div class=r><a class=navlink href="journal.html">JOURNAL PREVIEW</a><span class=tag>STATIC - DEMO DATA</span></div></header>
 <div class=symbar>
   <div class=symseg id=symSeg><button data-s=BTCUSDT class=act>BTC</button></div>
   <span class=label>perpetual - binance futures - frozen snapshot</span>
 </div>
 <section class="hero demo-hero">
  <div class=bigprice id=px>${last_close:,.1f}</div>
  <div class="pxsub rv d1"><b id=chg style="color:{'var(--up)' if chg>=0 else 'var(--down)'}">{chg:+.2f}%</b> over this window &nbsp;.&nbsp; {len(trades)} v20 trades shown &nbsp;.&nbsp; strategy stats below</div>
 </section>
 <section class="panel rv d2">
  <div class=panel-h><span class=t><span class=sq></span>BTC - V20 STRATEGY 15M ({perf['n']} trades - WR {perf['wr']}% - RET +{perf['ret']}%)</span></div>
  <div id=chart style="height:460px"></div>
  <div id=rsi style="height:110px;margin-top:6px"></div>
 </section>
 <section class="panel rv d3" style="margin-top:16px">
  <div class=panel-h><span class=t><span class=sq></span>Full six-year backtest (real numbers, not this window)</span></div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:14px;font-size:12px">
   <div><div class=label>Return</div><div style="font-size:20px;color:var(--up);font-weight:600">+{perf['ret']}%</div></div>
   <div><div class=label>Max drawdown</div><div style="font-size:20px;font-weight:600">{perf['maxdd']}%</div></div>
   <div><div class=label>Win rate</div><div style="font-size:20px;font-weight:600">{perf['wr']}%</div></div>
   <div><div class=label>Calmar</div><div style="font-size:20px;font-weight:600">{perf['cal']}</div></div>
   <div><div class=label>Trades</div><div style="font-size:20px;font-weight:600">{perf['n']}</div></div>
  </div>
  <p style="font-size:11px;color:var(--dim);margin-top:12px;line-height:1.6">This box is real - it's the actual backtest result from the strategy engine (<code>eng.py</code> + <code>bot_v20_funding.py</code>), same code the live bot runs. The chart above shows a frozen 3000-bar window of real historical BTC price action with the strategy's real entries/exits from that window overlaid, so you can see what the boxes actually mean. Full methodology and every rejected idea: <code>CLAUDE.md</code> in the repo.</p>
 </section>
 <footer class=foot><span>Static preview - <a href="{REPO_URL}" style="color:var(--dim)">{REPO_URL.split('//')[1]}</a></span><span>IBM Plex Mono - Bricolage Grotesque</span><span id=ts>-</span></footer>
</div>
<script>
const $=id=>document.getElementById(id);
const BARS={bars_json};
const TRADES={trades_json};
function fp(n){{const d=n<5?4:n<100?3:1;return '$'+Number(n).toLocaleString('en-US',{{minimumFractionDigits:d,maximumFractionDigits:d}});}}
class TradeBoxes{{
 constructor(){{this._t=[];this._u=null;}}
 attached(p){{this._u=p.requestUpdate;}} detached(){{this._u=null;}}
 set(t){{this._t=t||[];if(this._u)this._u();}}
 updateAllViews(){{}} paneViews(){{return [this];}} zOrder(){{return 'bottom';}} renderer(){{return this;}}
 draw(target){{const t=this._t,ts=chart.timeScale();target.useBitmapCoordinateSpace(s=>{{const ctx=s.context,hr=s.horizontalPixelRatio,vr=s.verticalPixelRatio;
  t.forEach(o=>{{let x1=ts.timeToCoordinate(o.et),x2=ts.timeToCoordinate(o.xt);if(x1==null||x2==null)return;if(x2<=x1)x2=x1+8;
   const ye=candleS.priceToCoordinate(o.entry),yt=candleS.priceToCoordinate(o.tp),ysl=candleS.priceToCoordinate(o.sl);if(ye==null)return;
   const X1=x1*hr,W=(x2-x1)*hr,Ye=ye*vr;
   if(yt!=null){{ctx.fillStyle='rgba(39,208,122,0.13)';ctx.fillRect(X1,Math.min(Ye,yt*vr),W,Math.abs(yt*vr-Ye));}}
   if(ysl!=null){{ctx.fillStyle='rgba(255,69,58,0.13)';ctx.fillRect(X1,Math.min(Ye,ysl*vr),W,Math.abs(ysl*vr-Ye));}}
   ctx.lineWidth=Math.max(1,hr);
   ctx.strokeStyle='rgba(255,180,84,0.9)';ctx.beginPath();ctx.moveTo(X1,Ye);ctx.lineTo(X1+W,Ye);ctx.stroke();
   if(yt!=null){{ctx.strokeStyle='rgba(39,208,122,0.85)';ctx.beginPath();ctx.moveTo(X1,yt*vr);ctx.lineTo(X1+W,yt*vr);ctx.stroke();}}
   if(ysl!=null){{ctx.strokeStyle='rgba(255,69,58,0.85)';ctx.beginPath();ctx.moveTo(X1,ysl*vr);ctx.lineTo(X1+W,ysl*vr);ctx.stroke();}}
  }});}});}}
}}
const base={{layout:{{background:{{color:'transparent'}},textColor:'#8a7f63',fontFamily:'IBM Plex Mono',fontSize:11}},grid:{{vertLines:{{color:'rgba(255,140,26,.03)'}},horzLines:{{color:'rgba(255,140,26,.03)'}}}},timeScale:{{timeVisible:true,borderColor:'#1b1810'}},rightPriceScale:{{borderColor:'#1b1810'}},crosshair:{{mode:0}}}};
const chart=LightweightCharts.createChart($('chart'),base);
chart.applyOptions({{localization:{{priceFormatter:fp}}}});
const candleS=chart.addCandlestickSeries({{upColor:'#27d07a',downColor:'#ff453a',borderVisible:false,wickUpColor:'#27d07a',wickDownColor:'#ff453a'}});
const volS=chart.addHistogramSeries({{priceFormat:{{type:'volume'}},priceScaleId:'vol'}});volS.priceScale().applyOptions({{scaleMargins:{{top:0.84,bottom:0}}}});
const boxes=new TradeBoxes();candleS.attachPrimitive(boxes);
candleS.setData(BARS.map(k=>({{time:k.time,open:k.open,high:k.high,low:k.low,close:k.close}})));
volS.setData(BARS.map(k=>({{time:k.time,value:k.volume,color:k.close>=k.open?'rgba(39,208,122,.32)':'rgba(255,69,58,.32)'}})));
boxes.set(TRADES);
const markers=TRADES.map(o=>({{time:o.et,position:o.dir>0?'belowBar':'aboveBar',color:o.dir>0?'#27d07a':'#ff453a',shape:o.dir>0?'arrowUp':'arrowDown',text:(o.dir>0?'LONG':'SHORT')+' '+o.ret.toFixed(1)+'%'}}));
candleS.setMarkers(markers);
chart.timeScale().fitContent();
const rsiChart=LightweightCharts.createChart($('rsi'),Object.assign({{}},base,{{timeScale:{{visible:false,borderColor:'#1b1810'}}}}));
function RSI(c,p){{p=p||14;let o=Array(c.length).fill(null),g=0,l=0;for(let i=1;i<=p;i++){{const d=c[i]-c[i-1];if(d>=0)g+=d;else l-=d;}}g/=p;l/=p;o[p]=100-100/(1+g/(l||1e-9));for(let i=p+1;i<c.length;i++){{const d=c[i]-c[i-1];g=(g*(p-1)+(d>0?d:0))/p;l=(l*(p-1)+(d<0?-d:0))/p;o[i]=100-100/(1+g/(l||1e-9));}}return o;}}
const closes=BARS.map(k=>k.close), rsiArr=RSI(closes,14);
const rsiS=rsiChart.addLineSeries({{color:'#ffb454',lineWidth:1.5,priceLineVisible:false}});
rsiS.createPriceLine({{price:70,color:'rgba(255,69,58,.4)',lineStyle:2,lineWidth:1}});rsiS.createPriceLine({{price:30,color:'rgba(39,208,122,.4)',lineStyle:2,lineWidth:1}});
rsiS.setData(BARS.map((k,i)=>({{time:k.time,value:rsiArr[i]}})).filter(x=>x.value!=null));
chart.timeScale().subscribeVisibleLogicalRangeChange(r=>{{if(r)try{{rsiChart.timeScale().setVisibleLogicalRange(r);}}catch(e){{}}}});
function clk(){{$('ts').textContent=new Date().toUTCString().slice(5,22)+' UTC'}}
clk();setInterval(clk,1000);
</script></body></html>"""
    with open(os.path.join(HERE, "index.html"), "w") as f:
        f.write(html)
    print(f"docs/index.html written ({len(bars)} bars, {len(trades)} trades)")


def build_journal():
    import datetime
    now_dt = datetime.datetime.now()
    demo = [
        (2, 1, "BTCUSDT", 500, 60250, 61180, 20, "Breakout RSI + pullback confirm, TP di resistance minor"),
        (5, -1, "ETHUSDT", 400, 3410, 3465, 15, "Short kena SL, salah baca momentum jangka pendek"),
        (8, 1, "BTCUSDT", 500, 58900, 59610, 10, "Entry di golden pocket setelah retrace, disiplin ikutin plan"),
        (12, 1, "SOLUSDT", 300, 142.5, 145.8, 8, "Trend day, exit sebagian di TP1"),
        (15, -1, "BTCUSDT", 500, 61500, 61080, 20, "Choppy market, entry kepagian sebelum konfirmasi"),
        (18, 1, "ETHUSDT", 400, 3280, 3355, 15, "Momentum breakout bersih, TP kena cepat"),
        (22, 1, "BTCUSDT", 500, 59800, 60920, 12, "Reversal dari support kuat, R:R bagus"),
        (25, -1, "ETHUSDT", 400, 3300, 3345, 15, "SL kena, momentum lemah dari awal"),
        (27, -1, "SOLUSDT", 300, 148.2, 150.1, 8, "Whipsaw, kena stop sebelum lanjut arah semula"),
    ]
    entries = []
    for i, (day, dirn, sym, modal, entry, exit_, lev, note) in enumerate(demo):
        dt = now_dt.replace(day=min(day, 28), hour=13, minute=30, second=0, microsecond=0)
        ts = int(dt.timestamp())
        pnl = round(modal * lev * ((exit_ - entry) / entry) * dirn, 2)
        entries.append({"id": f"demo{i}", "ts": ts, "note": note, "sym": sym, "img": None,
                         "modal": modal, "entry": entry, "exit": exit_, "sl": None, "lev": lev,
                         "dir": dirn, "pnl": pnl})
    total = sum(e["pnl"] for e in entries)
    wins = sum(1 for e in entries if e["pnl"] > 0)
    wr = round(wins / len(entries) * 100)

    html = HEAD + "<style>" + BANNER_CSS + "</style><title>DNAYAKA - Journal (static preview)</title></head><body>" + ATMOS + banner("journal") + f"""
<div class=wrap style="max-width:640px">
 <header class=hdr><div class=brand><span class=bt style="font-size:15px">&#128203;</span> DNAYAKA<span style="color:var(--dim);font-weight:400;font-size:11px;letter-spacing:.18em;text-transform:uppercase;margin-left:9px">Trading Journal</span><span class=cur></span></div>
  <div class=r><a class=navlink href="index.html">TERMINAL PREVIEW</a><span class=tag>STATIC - DEMO DATA</span></div></header>
 <section class="panel rv d1" style="margin-top:16px;overflow:hidden;position:relative;text-align:center;padding:26px 20px;background:radial-gradient(120% 140% at 50% -20%,rgba(255,140,26,.10),transparent 60%),var(--panel)">
  <div class=label style="letter-spacing:.24em">Total PnL</div>
  <div id=pnlBig class=bigprice style="font-size:clamp(34px,8vw,58px);margin:8px 0 4px;color:{'var(--up)' if total>=0 else 'var(--down)'};text-shadow:0 0 44px {'rgba(39,208,122,.35)' if total>=0 else 'rgba(255,69,58,.35)'}">{'+' if total>=0 else '-'}${abs(total):,.2f}</div>
  <div style="display:flex;justify-content:center;gap:22px;flex-wrap:wrap;margin-top:6px;font-size:11.5px;color:var(--dim)">
   <span>Win rate <b style="color:var(--ink)">{wr}%</b></span>
   <span>Trade tercatat <b style="color:var(--ink)">{len(entries)}</b></span>
  </div>
 </section>
 <section class="panel rv d3" style="margin-top:16px">
  <div class=panel-h><span class=t><span class=sq></span>Kalender PnL (bulan berjalan, demo)</span></div>
  <div id=calGrid style="display:grid;grid-template-columns:repeat(7,1fr);gap:5px"></div>
  <div style="display:flex;justify-content:center;gap:14px;margin-top:10px;font-size:10px;color:var(--dim)"><span><span style="display:inline-block;width:8px;height:8px;background:var(--up);border-radius:2px;margin-right:4px"></span>profit</span><span><span style="display:inline-block;width:8px;height:8px;background:var(--down);border-radius:2px;margin-right:4px"></span>loss</span></div>
 </section>
 <section class="panel rv d3" style="margin-top:16px">
  <div class=panel-h><span class=t><span class=sq></span>Riwayat (contoh - di app asli ini privat per-akun)</span></div>
  <div id=jlist style="display:flex;flex-direction:column;gap:10px"></div>
 </section>
 <footer class=foot><span>Static preview - <a href="{REPO_URL}" style="color:var(--dim)">{REPO_URL.split('//')[1]}</a></span><span>Semua angka di halaman ini dummy</span><span id=ts>-</span></footer>
</div>
<div id=cardModal style="display:none;position:fixed;inset:0;z-index:300;background:rgba(0,0,0,.82);align-items:center;justify-content:center;padding:16px;flex-direction:column;gap:14px">
 <canvas id=shareCanvas style="max-width:100%;max-height:70vh;border-radius:12px;box-shadow:0 30px 80px rgba(0,0,0,.7)"></canvas>
 <div style="display:flex;gap:10px">
  <button onclick=downloadCard() style="padding:11px 20px;font-family:var(--mono);font-weight:600;letter-spacing:.08em;text-transform:uppercase;background:var(--amber);color:#160c00;border:0;border-radius:7px;cursor:pointer;font-size:12px">Download PNG</button>
  <button onclick=closeCard() style="padding:11px 20px;font-family:var(--mono);font-weight:600;letter-spacing:.08em;text-transform:uppercase;background:transparent;color:var(--dim);border:1px solid var(--line);border-radius:7px;cursor:pointer;font-size:12px">Tutup</button>
 </div>
</div>
<script>
const $=id=>document.getElementById(id);
function esc(s){{return String(s==null?'':s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[c])}}
const ENTRIES={json.dumps(entries)};
function fmtMoney(n){{const s=Math.abs(n)>=1000?Number(n.toFixed(0)).toLocaleString():n.toFixed(2);return (n>=0?'+':'-')+'$'+s}}
function renderCalendar(){{
 const now=new Date(); const calYear=now.getFullYear(), calMonth=now.getMonth();
 const byDay={{}};
 ENTRIES.forEach(e=>{{const d=new Date(e.ts*1000);if(d.getFullYear()!==calYear||d.getMonth()!==calMonth)return;const key=d.getDate();const b=byDay[key]||{{pnl:0,n:0,has:false}};b.n++;b.has=true;b.pnl+=e.pnl;byDay[key]=b;}});
 const first=new Date(calYear,calMonth,1); const startDow=first.getDay(); const daysInMonth=new Date(calYear,calMonth+1,0).getDate();
 let html=['Min','Sen','Sel','Rab','Kam','Jum','Sab'].map(d=>'<div style="text-align:center;font-size:9px;color:var(--dim);letter-spacing:.1em;padding-bottom:4px">'+d+'</div>').join('');
 for(let i=0;i<startDow;i++) html+='<div></div>';
 for(let day=1;day<=daysInMonth;day++){{
  const b=byDay[day]; let bg='var(--bg)', bd='var(--line)', txtcol='var(--dim)';
  if(b&&b.has){{ if(b.pnl>0){{bg='rgba(39,208,122,.16)';bd='var(--up)'}} else if(b.pnl<0){{bg='rgba(255,69,58,.16)';bd='var(--down)'}} txtcol='var(--ink)' }}
  html+='<div style="aspect-ratio:1;border:1px solid '+bd+';background:'+bg+';border-radius:5px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;padding:2px">'
   +'<span style="font-size:10px;color:'+txtcol+'">'+day+'</span>'
   +(b&&b.has?('<span style="font-size:8.5px;font-weight:600;color:'+(b.pnl>0?'var(--up)':'var(--down)')+'">'+fmtMoney(b.pnl)+'</span>'):'')
   +'</div>';
 }}
 $('calGrid').innerHTML=html;
}}
function renderList(){{
 const es=ENTRIES.slice().sort((a,b)=>b.ts-a.ts);
 $('jlist').innerHTML=es.map(e=>{{
  const dtxt=new Date(e.ts*1000).toLocaleDateString();
  const symtag='<span class=tag style="margin-right:8px">'+esc(e.sym)+'</span>';
  const stat=[];
  stat.push('<span>PnL <b style="color:'+(e.pnl>=0?'var(--up)':'var(--down)')+'">'+(e.pnl>=0?'+':'')+'$'+Number(e.pnl).toLocaleString()+'</b></span>');
  stat.push('<span><b style="color:'+(e.dir===-1?'var(--down)':'var(--up)')+'">'+(e.dir===-1?'SHORT':'LONG')+'</b></span>');
  stat.push('<span>Modal <b style="color:var(--ink)">$'+Number(e.modal).toLocaleString()+'</b></span>');
  stat.push('<span>Lev <b style="color:var(--amber)">'+Number(e.lev)+'x</b></span>');
  return '<div style="border:1px solid var(--line);border-radius:6px;padding:11px">'
   +'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px"><span style="font-size:10.5px;color:var(--dim)">'+symtag+esc(dtxt)+'</span>'
   +'<button onclick="showCard(\\''+e.id+'\\')" style="background:none;border:1px solid var(--amber);color:var(--amber);border-radius:4px;cursor:pointer;font-size:10px;padding:3px 8px">pamer</button></div>'
   +'<div style="font-size:11.5px;color:var(--dim);margin-top:7px;display:flex;gap:14px;flex-wrap:wrap">'+stat.join('')+'</div>'
   +'<div style="font-size:12.5px;margin-top:7px;line-height:1.5">'+esc(e.note)+'</div></div>';
 }}).join('');
}}
function roundRect(ctx,x,y,w,h,r){{ctx.beginPath();ctx.moveTo(x+r,y);ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath()}}
function drawShareCard(e){{
 const c=$('shareCanvas'), W=960, H=600, dpr=Math.min(2,window.devicePixelRatio||1);
 c.width=W*dpr; c.height=H*dpr; c.style.width=W+'px'; c.style.height=H+'px';
 const ctx=c.getContext('2d'); ctx.scale(dpr,dpr);
 const up=e.pnl>=0, col=up?'#27d07a':'#ff453a', colGlow=up?'rgba(39,208,122,.28)':'rgba(255,69,58,.28)';
 ctx.fillStyle='#040302'; ctx.fillRect(0,0,W,H);
 const rg=ctx.createRadialGradient(W/2,-40,40,W/2,H*0.35,W*0.75);
 rg.addColorStop(0,colGlow); rg.addColorStop(1,'rgba(0,0,0,0)');
 ctx.fillStyle=rg; ctx.fillRect(0,0,W,H);
 ctx.strokeStyle='rgba(255,140,26,.35)'; ctx.lineWidth=1.5; roundRect(ctx,10,10,W-20,H-20,16); ctx.stroke();
 ctx.fillStyle='#ff8c1a'; ctx.font='700 20px monospace'; ctx.fillText('DNAYAKA', 44, 62);
 ctx.fillStyle='#8a7f63'; ctx.font='500 12px monospace'; ctx.fillText('TRADING JOURNAL (demo)', 44, 80);
 const badge=(e.sym||'TRADE')+'  '+(e.dir===-1?'SHORT':'LONG');
 ctx.textAlign='right'; ctx.font='600 15px monospace'; ctx.fillStyle=e.dir===-1?'#ff453a':'#27d07a';
 ctx.fillText(badge, W-44, 66); ctx.textAlign='left';
 ctx.fillStyle='#8a7f63'; ctx.font='500 12px monospace'; ctx.textAlign='right';
 ctx.fillText(new Date(e.ts*1000).toLocaleDateString(), W-44, 84); ctx.textAlign='left';
 const pnlTxt=(up?'+':'-')+'$'+Math.abs(e.pnl).toLocaleString(undefined,{{minimumFractionDigits:2,maximumFractionDigits:2}});
 ctx.textAlign='center'; ctx.fillStyle=col; ctx.font='700 96px monospace';
 ctx.shadowColor=colGlow; ctx.shadowBlur=50;
 ctx.fillText(pnlTxt, W/2, 300); ctx.shadowBlur=0;
 if(e.modal){{const pct=(e.pnl/e.modal*100); ctx.font='500 17px monospace'; ctx.fillStyle='#e8e2d0'; ctx.fillText((pct>=0?'+':'')+pct.toFixed(2)+'% return dari modal', W/2, 336);}}
 ctx.textAlign='left';
 const stats=[['ENTRY','$'+Number(e.entry).toLocaleString()],['EXIT','$'+Number(e.exit).toLocaleString()],['LEVERAGE',Number(e.lev)+'x'],['MODAL','$'+Number(e.modal).toLocaleString()]];
 const n=stats.length,colW=(W-88)/n;
 stats.forEach((s,i)=>{{const cx=44+colW*i;
  if(i>0){{ctx.strokeStyle='rgba(255,255,255,.08)';ctx.beginPath();ctx.moveTo(cx,410);ctx.lineTo(cx,470);ctx.stroke()}}
  ctx.fillStyle='#8a7f63'; ctx.font='600 11px monospace'; ctx.fillText(s[0], cx+(i>0?18:0), 430);
  ctx.fillStyle='#e8e2d0'; ctx.font='700 22px monospace'; ctx.fillText(s[1], cx+(i>0?18:0), 460);
 }});
 ctx.fillStyle='#8a7f63'; ctx.font='italic 13px monospace';
 ctx.fillText('"'+e.note+'"', 44, 520);
 ctx.fillStyle='rgba(255,140,26,.5)'; ctx.font='500 10px monospace'; ctx.textAlign='right';
 ctx.fillText('dnayaka trading journal - static demo', W-44, H-30);
}}
let curCardEntry=null;
function showCard(id){{const e=ENTRIES.find(x=>x.id===id); if(!e) return; curCardEntry=e; drawShareCard(e); $('cardModal').style.display='flex';}}
function closeCard(){{$('cardModal').style.display='none'}}
function downloadCard(){{if(!curCardEntry) return; const c=$('shareCanvas'); const a=document.createElement('a'); a.download='pnl-demo-'+curCardEntry.id+'.png'; a.href=c.toDataURL('image/png'); a.click();}}
function clk(){{$('ts').textContent=new Date().toUTCString().slice(5,22)+' UTC'}}
renderCalendar();renderList();clk();setInterval(clk,1000);
</script></body></html>"""
    with open(os.path.join(HERE, "journal.html"), "w") as f:
        f.write(html)
    print(f"docs/journal.html written ({len(entries)} demo entries, total {'+' if total>=0 else ''}{total:.2f})")


if __name__ == "__main__":
    build_terminal()
    build_journal()
