#!/usr/bin/env python3
"""BTC TERMINAL — PUBLIC market dashboard :8788. Multi-asset BTC/ETH/SOL. READ-ONLY (no keys, no trading).
Aman dishare/deploy publik. Kontrol trading privat ada di config_admin.py (localhost:8789)."""
import json, requests, urllib3, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
urllib3.disable_warnings()
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0'}); FAPI="https://fapi.binance.com"
SYMS={"BTCUSDT","ETHUSDT","SOLUSDT"}; _G={"t":0,"d":{}}; NEWSTAG={"BTCUSDT":"bitcoin","ETHUSDT":"ethereum","SOLUSDT":"solana"}
def sym_of(p): s=parse_qs(p.query).get("sym",["BTCUSDT"])[0].upper(); return s if s in SYMS else "BTCUSDT"

CSS=r"""
:root{--bg:#000000;--panel:#070707;--ink:#e8e2d0;--dim:#8a7f63;--faint:#3a3526;
--amber:#ff8c1a;--amber2:#ffb454;--glow:rgba(255,140,26,.45);--up:#27d07a;--down:#ff453a;--line:#1b1810;
--mono:'IBM Plex Mono',ui-monospace,monospace;--disp:'Bricolage Grotesque',sans-serif;}
*{margin:0;padding:0;box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{background:var(--bg);color:var(--ink);font-family:var(--mono);font-size:13px;line-height:1.35;overflow-x:hidden;letter-spacing:.01em}
.bg{position:fixed;inset:0;z-index:-3;background:radial-gradient(120% 70% at 50% -15%,rgba(255,140,26,.07),transparent 50%),radial-gradient(80% 60% at 90% 120%,rgba(39,208,122,.03),transparent 60%),var(--bg)}
.bg::before{content:"";position:absolute;inset:0;background-image:radial-gradient(rgba(255,140,26,.035) 1px,transparent 1px);background-size:34px 34px;-webkit-mask:radial-gradient(120% 80% at 50% 0%,#000,transparent 80%);mask:radial-gradient(120% 80% at 50% 0%,#000,transparent 80%)}
.scan{position:fixed;inset:0;z-index:-2;pointer-events:none;background:repeating-linear-gradient(0deg,transparent 0 2px,rgba(0,0,0,.22) 2px 3.5px);opacity:.4;mix-blend-mode:multiply}
.grain{position:fixed;inset:0;z-index:99;pointer-events:none;opacity:.035;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
.vig{position:fixed;inset:0;z-index:-1;pointer-events:none;box-shadow:inset 0 0 200px 30px rgba(0,0,0,.8)}
.boot{position:fixed;left:0;right:0;top:0;height:2px;background:linear-gradient(90deg,transparent,var(--amber),transparent);z-index:200;animation:boot 1s ease-out forwards}
@keyframes boot{0%{top:0;opacity:1}100%{top:100%;opacity:0}}
.wrap{max-width:1200px;margin:0 auto;padding:0 clamp(14px,3vw,28px) 50px}
.label{font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim)}
.up{color:var(--up)}.down{color:var(--down)}.amber{color:var(--amber)}
.fnbar{display:flex;gap:0;border-bottom:1px solid var(--line);font-size:10px;letter-spacing:.12em;color:var(--dim);overflow-x:auto}
.fnbar span{padding:5px 12px;border-right:1px solid var(--line);white-space:nowrap;text-transform:uppercase}
.fnbar span b{color:var(--amber);font-weight:600}
.hdr{display:flex;justify-content:space-between;align-items:center;padding:13px 0;border-bottom:1px solid var(--line);position:sticky;top:0;background:rgba(0,0,0,.88);backdrop-filter:blur(6px);z-index:50}
.brand{font-family:var(--disp);font-weight:700;font-size:15px;letter-spacing:-.01em;display:flex;align-items:center;gap:8px;color:var(--ink)}
.brand .bt{color:var(--amber);font-size:18px;text-shadow:0 0 12px var(--glow)}
.brand .cur{display:inline-block;width:8px;height:15px;background:var(--amber);margin-left:2px;animation:blink 1.1s step-end infinite;box-shadow:0 0 9px var(--glow)}
@keyframes blink{50%{opacity:0}}
.hdr .r{display:flex;align-items:center;gap:12px;font-size:10.5px;color:var(--dim)}
.tag{padding:3px 9px;border:1px solid var(--line);border-radius:2px;letter-spacing:.14em;font-size:10px;color:var(--amber)}
.symbar{display:flex;align-items:center;gap:10px;margin:18px 0 0;flex-wrap:wrap}
.symseg{display:flex;border:1px solid var(--line);border-radius:5px;overflow:hidden}
.symseg button{background:transparent;color:var(--dim);border:0;border-right:1px solid var(--line);padding:9px 20px;font-family:var(--disp);font-weight:600;font-size:15px;cursor:pointer;transition:.2s}
.symseg button:last-child{border-right:0}.symseg button:hover{color:var(--ink);background:rgba(255,140,26,.06)}
.symseg button.act{color:#160c00;background:var(--amber)}
/* hero — more breathing room for the ticker */
.hero{padding:30px 0 26px}
.bigprice{font-family:var(--mono);font-weight:600;font-size:clamp(46px,11vw,104px);line-height:1;letter-spacing:-.03em;margin:0 0 12px;font-variant-numeric:tabular-nums;color:var(--ink);text-shadow:0 0 44px rgba(255,140,26,.14);white-space:nowrap}
.bigprice.flash{animation:flash .5s}@keyframes flash{0%{color:var(--amber2);text-shadow:0 0 54px var(--glow)}100%{}}
.pxsub{font-size:14px;color:var(--dim)}.pxsub b{font-weight:600;font-variant-numeric:tabular-nums}
.gauges{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:9px;margin-top:24px}
.gauge{background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:12px 14px;position:relative;overflow:hidden}
.gauge::after{content:"";position:absolute;left:0;top:0;width:2px;height:100%;background:var(--amber);opacity:.7}
.gauge .g-l{font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.gauge .g-v{font-family:var(--mono);font-weight:600;font-size:20px;margin-top:5px;font-variant-numeric:tabular-nums}
.fngbar{height:3px;border-radius:2px;background:var(--faint);margin-top:8px;overflow:hidden}
.fngbar i{display:block;height:100%;background:linear-gradient(90deg,var(--down),var(--amber),var(--up));width:0;transition:width 1s}
.grid{display:grid;grid-template-columns:1fr;gap:10px;margin-top:10px}
@media(min-width:880px){.grid{grid-template-columns:1.6fr 1fr}.span2{grid-column:1/3}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px;position:relative}
.panel-h{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px}
.panel-h .t{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--amber);display:flex;align-items:center;gap:7px}
.panel-h .t .sq{width:5px;height:5px;background:var(--amber);box-shadow:0 0 7px var(--glow)}
.ctrls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.seg{display:flex;gap:3px}
.seg button{background:transparent;color:var(--dim);border:1px solid var(--line);padding:4px 10px;border-radius:3px;font-family:var(--mono);font-size:10.5px;cursor:pointer;transition:.2s;letter-spacing:.05em}
.seg button:hover{color:var(--ink);border-color:var(--faint)}.seg button.act{color:var(--amber);border-color:var(--amber);background:rgba(255,140,26,.08)}
#chart{height:340px;border-radius:4px;overflow:hidden}
#rsi{height:100px;border-radius:4px;overflow:hidden;margin-top:3px;border-top:1px solid var(--line)}
.rsi-l{font-size:9px;letter-spacing:.14em;color:var(--dim);margin:5px 0 -2px;text-transform:uppercase}
.liqbar{height:28px;border-radius:4px;overflow:hidden;display:flex;margin:4px 0 12px;border:1px solid var(--line)}
.liqbar .b{background:linear-gradient(90deg,rgba(39,208,122,.12),rgba(39,208,122,.4));display:flex;align-items:center;padding:0 9px;font-size:10.5px;color:var(--up);font-weight:600;transition:flex .8s}
.liqbar .a{background:linear-gradient(90deg,rgba(255,69,58,.4),rgba(255,69,58,.12));display:flex;align-items:center;justify-content:flex-end;padding:0 9px;font-size:10.5px;color:var(--down);font-weight:600;transition:flex .8s}
.liqrow{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--line);font-size:12.5px}
.liqrow:last-child{border-bottom:0}.liqrow .k{color:var(--dim);font-size:10px;letter-spacing:.1em;text-transform:uppercase}.liqrow .v{font-weight:600;font-variant-numeric:tabular-nums}
.wall{display:flex;justify-content:space-between;font-size:11.5px;color:var(--dim);padding:5px 0}.wall b{color:var(--ink)}
.statg{display:grid;grid-template-columns:1fr 1fr;gap:9px}
.statg .s{background:var(--bg);border:1px solid var(--line);border-radius:5px;padding:11px 12px}
.statg .s .k{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim)}
.statg .s .v{font-size:17px;font-weight:600;margin-top:4px;font-variant-numeric:tabular-nums}
.wire a{display:grid;grid-template-columns:auto 1fr;gap:11px;padding:10px 0;border-bottom:1px solid var(--line);color:var(--ink);text-decoration:none;font-size:13px;line-height:1.4;transition:.2s}
.wire a:hover{color:var(--amber2);padding-left:5px}.wire a:last-child{border-bottom:0}
.wire a .ago{font-size:9.5px;color:var(--amber);letter-spacing:.1em;padding-top:2px;min-width:32px}.wire a .src{font-size:9.5px;color:var(--dim)}
.foot{margin-top:26px;padding-top:16px;border-top:1px solid var(--line);display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px}
.foot span{font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint)}
.rv{opacity:0;transform:translateY(14px);animation:rv .7s cubic-bezier(.2,.8,.2,1) forwards}@keyframes rv{to{opacity:1;transform:none}}
.d1{animation-delay:.1s}.d2{animation-delay:.2s}.d3{animation-delay:.3s}.d4{animation-delay:.4s}.d5{animation-delay:.5s}
::selection{background:var(--amber);color:#0a0700}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:var(--line);border-radius:4px}
@media(max-width:620px){.gauges{grid-template-columns:1fr 1fr}.bigprice{white-space:normal}}
"""
HEAD=("<!doctype html><html lang=en><head><meta charset=utf-8>"
"<meta name=viewport content='width=device-width,initial-scale=1'>"
"<script src='https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js'></script>"
"<link rel=preconnect href=https://fonts.googleapis.com><link rel=preconnect href=https://fonts.gstatic.com crossorigin>"
"<link href='https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,300..800&family=IBM+Plex+Mono:wght@300;400;500;600;700&display=swap' rel=stylesheet>"
"<style>"+CSS+"</style>")
ATMOS="<div class=bg></div><div class=scan></div><div class=vig></div><div class=grain></div><div class=boot></div>"
MAIN=HEAD+"<title>CRYPTO // TERMINAL</title></head><body>"+ATMOS+r"""
<div class=fnbar><span><b>F1</b> MARKETS</span><span><b>F2</b> CHART</span><span><b>F3</b> LIQUIDITY</span><span><b>F4</b> STATS</span><span><b>F5</b> NEWS</span><span id=fnclock style="margin-left:auto;color:var(--amber)"></span></div>
<div class=wrap>
 <header class=hdr><div class=brand><span class=bt>₿</span> CRYPTO TERMINAL<span class=cur></span></div>
  <div class=r><span class=tag>PUBLIC · LIVE</span></div></header>
 <div class=symbar>
   <div class=symseg id=symSeg><button data-s=BTCUSDT class=act>BTC</button><button data-s=ETHUSDT>ETH</button><button data-s=SOLUSDT>SOL</button></div>
   <span class=label id=symlbl>perpetual · binance futures</span>
 </div>
 <section class=hero>
  <div class=bigprice id=px>------</div>
  <div class="pxsub rv d1"><b id=chg>—</b> 24H &nbsp;·&nbsp; MARK <b id=mark>—</b></div>
  <div class=gauges>
   <div class="gauge rv d2"><div class=g-l>Funding 8h</div><div class=g-v id=funding>—</div></div>
   <div class="gauge rv d3"><div class=g-l>Fear &amp; Greed</div><div class=g-v id=fng>—</div><div class=fngbar><i id=fngbar></i></div></div>
   <div class="gauge rv d4"><div class=g-l>Open Interest</div><div class=g-v id=oi style="font-size:16px">—</div></div>
   <div class="gauge rv d5"><div class=g-l>Long / Short</div><div class=g-v id=ls style="font-size:16px">—</div></div>
   <div class="gauge rv d5"><div class=g-l>BTC Dominance</div><div class=g-v id=dom style="font-size:18px">—</div><div class=fngbar><i id=dombar></i></div></div>
  </div>
 </section>
 <div class=grid>
  <section class="panel span2 rv d2">
   <div class=panel-h><span class=t><span class=sq></span><span id=chtitle>BTC · Price Action</span></span>
    <div class=ctrls><div class=seg id=typeSeg><button data-ty=candle class=act>Candles</button><button data-ty=line>Line</button></div>
     <div class=seg id=tfSeg><button data-tf=15m class=act>15m</button><button data-tf=1h>1h</button><button data-tf=4h>4h</button><button data-tf=1d>1d</button></div></div></div>
   <div id=chart></div><div class=rsi-l>RSI · 14</div><div id=rsi></div>
  </section>
  <section class="panel rv d3">
   <div class=panel-h><span class=t><span class=sq></span>Liquidity · Order Book</span></div>
   <div class=label>Bid vs Ask depth (±2%)</div>
   <div class=liqbar><div class=b id=lqb style="flex:1"></div><div class=a id=lqa style="flex:1"></div></div>
   <div class=wall><span>BID WALL</span><span><b id=bidwall>—</b></span></div>
   <div class=wall><span>ASK WALL</span><span><b id=askwall>—</b></span></div>
   <div class=liqrow><span class=k>Open Interest</span><span class=v id=oi2>—</span></div>
   <div class=liqrow><span class=k>Retail L/S</span><span class=v id=ls2>—</span></div>
   <div class=liqrow><span class=k>Top trader L/S</span><span class=v id=top2>—</span></div>
  </section>
  <section class="panel rv d3">
   <div class=panel-h><span class=t><span class=sq></span>24h Statistics</span></div>
   <div class=statg>
    <div class=s><div class=k>24h High</div><div class=v id=hi>—</div></div>
    <div class=s><div class=k>24h Low</div><div class=v id=lo>—</div></div>
    <div class=s><div class=k>24h Volume</div><div class=v id=vol>—</div></div>
    <div class=s><div class=k>24h Change</div><div class=v id=ch24>—</div></div>
   </div>
  </section>
  <section class="panel rv d4">
   <div class=panel-h><span class=t><span class=sq></span>Market Snapshot</span></div>
   <div class=liqrow><span class=k>Mark Price</span><span class=v id=mk2>—</span></div>
   <div class=liqrow><span class=k>Funding 8h</span><span class=v id=fnd2>—</span></div>
   <div class=liqrow><span class=k>Weighted Avg</span><span class=v id=wavg>—</span></div>
   <div class=liqrow><span class=k>Trades 24h</span><span class=v id=trades>—</span></div>
   <div class=liqrow><span class=k>Total Mcap</span><span class=v id=mcap>—</span></div>
   <div class=liqrow><span class=k>Mcap 24h</span><span class=v id=mcapch>—</span></div>
  </section>
  <section class="panel span2 rv d5">
   <div class=panel-h><span class=t><span class=sq></span><span id=newstitle>News Wire — BTC</span></span></div>
   <div class=wire id=news></div>
  </section>
 </div>
 <footer class=foot><span>Crypto Terminal · public</span><span>IBM Plex Mono · Bricolage Grotesque</span><span id=ts>—</span></footer>
</div>
<script>
const $=id=>document.getElementById(id);let chart,candleS,lineS,volS,rsiChart,rsiS,curTF='15m',cty='candle',sym='BTCUSDT',lastPx=0;
const SN={BTCUSDT:'BTC',ETHUSDT:'ETH',SOLUSDT:'SOL'};
function RSI(c,p){p=p||14;let o=Array(c.length).fill(null),g=0,l=0;for(let i=1;i<=p;i++){const d=c[i]-c[i-1];if(d>=0)g+=d;else l-=d;}g/=p;l/=p;o[p]=100-100/(1+g/(l||1e-9));for(let i=p+1;i<c.length;i++){const d=c[i]-c[i-1];g=(g*(p-1)+(d>0?d:0))/p;l=(l*(p-1)+(d<0?-d:0))/p;o[i]=100-100/(1+g/(l||1e-9));}return o;}
function fmt(n){return n>=1e9?(n/1e9).toFixed(2)+'B':n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':Math.round(n);}
function fp(n){const d=n<5?4:n<100?3:1;return '$'+Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});}
function initChart(){
 const base={layout:{background:{color:'transparent'},textColor:'#8a7f63',fontFamily:'IBM Plex Mono',fontSize:11},grid:{vertLines:{color:'rgba(255,140,26,.03)'},horzLines:{color:'rgba(255,140,26,.03)'}},timeScale:{timeVisible:true,borderColor:'#1b1810'},rightPriceScale:{borderColor:'#1b1810'},crosshair:{mode:0,vertLine:{color:'#ff8c1a66',labelBackgroundColor:'#ff8c1a'},horzLine:{color:'#ff8c1a66',labelBackgroundColor:'#ff8c1a'}}};
 chart=LightweightCharts.createChart($('chart'),base);
 candleS=chart.addCandlestickSeries({upColor:'#27d07a',downColor:'#ff453a',borderVisible:false,wickUpColor:'#27d07a',wickDownColor:'#ff453a'});
 lineS=chart.addLineSeries({color:'#ff8c1a',lineWidth:2,visible:false,priceLineVisible:false});
 volS=chart.addHistogramSeries({priceFormat:{type:'volume'},priceScaleId:'vol'});volS.priceScale().applyOptions({scaleMargins:{top:0.84,bottom:0}});
 rsiChart=LightweightCharts.createChart($('rsi'),Object.assign({},base,{timeScale:{visible:false,borderColor:'#1b1810'}}));
 rsiS=rsiChart.addLineSeries({color:'#ffb454',lineWidth:1.5,priceLineVisible:false});
 rsiS.createPriceLine({price:70,color:'rgba(255,69,58,.4)',lineStyle:2,lineWidth:1});rsiS.createPriceLine({price:30,color:'rgba(39,208,122,.4)',lineStyle:2,lineWidth:1});rsiS.createPriceLine({price:50,color:'rgba(138,127,99,.3)',lineStyle:3,lineWidth:1});
 chart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)rsiChart.timeScale().setVisibleLogicalRange(r);});
 rsiChart.timeScale().subscribeVisibleLogicalRangeChange(r=>{if(r)chart.timeScale().setVisibleLogicalRange(r);});
 loadChart();
}
function loadChart(){fetch('/api/klines?sym='+sym+'&tf='+curTF).then(r=>r.json()).then(d=>{
 candleS.setData(d.map(k=>({time:k.time,open:k.open,high:k.high,low:k.low,close:k.close})));
 lineS.setData(d.map(k=>({time:k.time,value:k.close})));
 volS.setData(d.map(k=>({time:k.time,value:k.volume,color:k.close>=k.open?'rgba(39,208,122,.32)':'rgba(255,69,58,.32)'})));
 const r=RSI(d.map(k=>k.close),14);rsiS.setData(d.map((k,i)=>r[i]!=null?{time:k.time,value:+r[i].toFixed(2)}:null).filter(Boolean));
 chart.timeScale().fitContent();
 if(d.length){const c=d[d.length-1].close;const e=$('px');e.textContent=fp(c);if(lastPx&&c!==lastPx){e.classList.remove('flash');void e.offsetWidth;e.classList.add('flash')}lastPx=c;}});}
$('typeSeg').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('typeSeg').querySelectorAll('button').forEach(x=>x.classList.remove('act'));b.classList.add('act');cty=b.dataset.ty;candleS.applyOptions({visible:cty=='candle'});lineS.applyOptions({visible:cty=='line'});});
$('tfSeg').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('tfSeg').querySelectorAll('button').forEach(x=>x.classList.remove('act'));b.classList.add('act');curTF=b.dataset.tf;loadChart();});
$('symSeg').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('symSeg').querySelectorAll('button').forEach(x=>x.classList.remove('act'));b.classList.add('act');sym=b.dataset.s;lastPx=0;$('chtitle').textContent=SN[sym]+' · Price Action';$('newstitle').textContent='News Wire — '+SN[sym];loadChart();loadMetrics();loadLiq();loadStats();loadNews();});
function loadMetrics(){fetch('/api/metrics?sym='+sym).then(r=>r.json()).then(m=>{const f=$('funding');f.textContent=(m.funding>=0?'+':'')+m.funding.toFixed(4)+'%';f.className='g-v '+(m.funding>=0?'up':'down');$('fnd2').textContent=(m.funding>=0?'+':'')+m.funding.toFixed(4)+'%';$('fng').textContent=m.fng+(m.fng_txt?' · '+m.fng_txt:'');$('fngbar').style.width=(parseInt(m.fng)||0)+'%';$('mark').textContent=fp(m.mark);$('mk2').textContent=fp(m.mark);});}
function loadLiq(){fetch('/api/liquidity?sym='+sym).then(r=>r.json()).then(d=>{if(d.imb!=null){$('lqb').style.flex=d.imb;$('lqa').style.flex=100-d.imb;$('lqb').textContent=Math.round(d.imb)+'% BID';$('lqa').textContent='ASK '+Math.round(100-d.imb)+'%';}if(d.bidWall)$('bidwall').textContent=d.bidWall[1].toFixed(1)+' @ '+Math.round(d.bidWall[0]);if(d.askWall)$('askwall').textContent=d.askWall[1].toFixed(1)+' @ '+Math.round(d.askWall[0]);if(d.oi!=null){const v=fmt(d.oi)+' '+SN[sym];$('oi').textContent=v;$('oi2').textContent=v;}if(d.ls){const t=d.ls.toFixed(2);$('ls').textContent=t;$('ls2').textContent=t+(d.ls>1?' ▲':' ▼');}if(d.top)$('top2').textContent=d.top.toFixed(2);});}
function loadStats(){fetch('/api/stats?sym='+sym).then(r=>r.json()).then(s=>{$('hi').textContent=fp(s.high);$('lo').textContent=fp(s.low);$('vol').textContent='$'+fmt(s.quoteVol);const c=$('ch24');c.textContent=(s.change>=0?'+':'')+s.change.toFixed(2)+'%';c.className='v '+(s.change>=0?'up':'down');const g=$('chg');g.textContent=(s.change>=0?'+':'')+s.change.toFixed(2)+'%';g.className=s.change>=0?'up':'down';$('wavg').textContent=fp(s.wavg);$('trades').textContent=fmt(s.trades);});}
function loadNews(){fetch('/api/news?sym='+sym).then(r=>r.json()).then(d=>{let h='';for(const n of d.slice(0,8))h+='<a href="'+n.url+'" target=_blank><span class=ago>'+n.ago+'</span><span>'+n.title+'<br><span class=src>'+n.source+'</span></span></a>';$('news').innerHTML=h||'<div style="color:var(--dim);font-size:12px">no wire</div>';});}
function clock(){const d=new Date();$('fnclock').textContent=d.toUTCString().slice(17,25)+' UTC';$('ts').textContent=d.toUTCString().slice(5,22)+' UTC';}
function loadGlobal(){fetch('/api/global').then(r=>r.json()).then(g=>{if(g.dom){$('dom').textContent=g.dom.toFixed(2)+'%';$('dombar').style.width=g.dom+'%';$('mcap').textContent='$'+g.mcap.toFixed(2)+'T';const c=$('mcapch');c.textContent=(g.mcapch>=0?'+':'')+g.mcapch.toFixed(2)+'%';c.className='v '+(g.mcapch>=0?'up':'down');}});}
initChart();loadMetrics();loadLiq();loadStats();loadNews();loadGlobal();clock();
setInterval(clock,1000);setInterval(loadChart,30000);setInterval(loadMetrics,30000);setInterval(loadLiq,20000);setInterval(loadStats,30000);setInterval(loadNews,300000);setInterval(loadGlobal,120000);
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _s(self,c,ct,b): self.send_response(c);self.send_header("Content-Type",ct);self.send_header("Access-Control-Allow-Origin","*");self.end_headers();self.wfile.write(b if isinstance(b,bytes) else b.encode())
    def do_GET(self):
        p=urlparse(self.path); path=p.path
        if path=="/": return self._s(200,"text/html",MAIN)
        if path=="/api/klines":
            sym=sym_of(p); tf=parse_qs(p.query).get("tf",["15m"])[0]
            try:
                r=S.get(FAPI+"/fapi/v1/klines",params={"symbol":sym,"interval":tf,"limit":500},timeout=12,verify=False)
                return self._s(200,"application/json",json.dumps([{"time":int(k[0]//1000),"open":float(k[1]),"high":float(k[2]),"low":float(k[3]),"close":float(k[4]),"volume":float(k[5])} for k in r.json()]))
            except: return self._s(200,"application/json","[]")
        if path=="/api/metrics":
            sym=sym_of(p); d={"funding":0,"mark":0,"fng":"-","fng_txt":""}
            try:
                j=S.get(FAPI+"/fapi/v1/premiumIndex?symbol="+sym,timeout=8,verify=False).json()
                d["funding"]=float(j["lastFundingRate"])*100; d["mark"]=float(j["markPrice"])
            except: pass
            try:
                f=S.get("https://api.alternative.me/fng/?limit=1",timeout=8,verify=False).json()["data"][0]
                d["fng"]=f["value"]; d["fng_txt"]=f["value_classification"].replace("Extreme ","E.")
            except: pass
            return self._s(200,"application/json",json.dumps(d))
        if path=="/api/global":
            import time
            if time.time()-_G["t"]>120:
                _G["t"]=time.time()   # stamp first so failures also respect the 120s window (no hammering on outage)
                try:
                    j=S.get("https://api.coingecko.com/api/v3/global",timeout=10,verify=False).json()["data"]
                    _G["d"]={"dom":j["market_cap_percentage"]["btc"],"mcap":j["total_market_cap"]["usd"]/1e12,"mcapch":j["market_cap_change_percentage_24h_usd"]}
                except: pass
            return self._s(200,"application/json",json.dumps(_G["d"]))
        if path=="/api/stats":
            sym=sym_of(p); d={"high":0,"low":0,"quoteVol":0,"change":0,"wavg":0,"trades":0}
            try:
                j=S.get(FAPI+"/fapi/v1/ticker/24hr?symbol="+sym,timeout=8,verify=False).json()
                d={"high":float(j["highPrice"]),"low":float(j["lowPrice"]),"quoteVol":float(j["quoteVolume"]),"change":float(j["priceChangePercent"]),"wavg":float(j["weightedAvgPrice"]),"trades":int(j["count"])}
            except: pass
            return self._s(200,"application/json",json.dumps(d))
        if path=="/api/liquidity":
            sym=sym_of(p); d={}
            try:
                ob=S.get(FAPI+"/fapi/v1/depth",params={"symbol":sym,"limit":100},timeout=8,verify=False).json()
                mid=(float(ob["bids"][0][0])+float(ob["asks"][0][0]))/2
                bl=sum(float(pp)*float(q) for pp,q in ob["bids"] if float(pp)>=mid*0.98)
                al=sum(float(pp)*float(q) for pp,q in ob["asks"] if float(pp)<=mid*1.02)
                if bl+al>0: d["imb"]=bl/(bl+al)*100
                bw=max(ob["bids"],key=lambda x:float(x[1])); aw=max(ob["asks"],key=lambda x:float(x[1]))
                d["bidWall"]=[float(bw[0]),float(bw[1])]; d["askWall"]=[float(aw[0]),float(aw[1])]
            except: pass
            try: d["oi"]=float(S.get(FAPI+"/fapi/v1/openInterest?symbol="+sym,timeout=8,verify=False).json()["openInterest"])
            except: pass
            try: d["ls"]=float(S.get(FAPI+"/futures/data/globalLongShortAccountRatio",params={"symbol":sym,"period":"5m","limit":1},timeout=8,verify=False).json()[-1]["longShortRatio"])
            except: pass
            try: d["top"]=float(S.get(FAPI+"/futures/data/topLongShortPositionRatio",params={"symbol":sym,"period":"5m","limit":1},timeout=8,verify=False).json()[-1]["longShortRatio"])
            except: pass
            return self._s(200,"application/json",json.dumps(d))
        if path=="/api/news":
            sym=sym_of(p); tag=NEWSTAG.get(sym,"bitcoin"); out=[]
            try:
                import xml.etree.ElementTree as ET
                from email.utils import parsedate_to_datetime
                r=S.get("https://cointelegraph.com/rss/tag/"+tag,timeout=12,verify=False)
                root=ET.fromstring(r.content); now=datetime.datetime.now(datetime.timezone.utc)
                for it in root.findall(".//item")[:10]:
                    t=(it.find("title").text or "").strip(); lk=(it.find("link").text or "").strip()
                    pd=it.find("pubDate"); ago="-"
                    if pd is not None and pd.text:
                        try:
                            mins=int((now-parsedate_to_datetime(pd.text)).total_seconds()/60)
                            ago=(f"{mins}m" if mins<60 else (f"{mins//60}h" if mins<1440 else f"{mins//1440}d"))
                        except: pass
                    out.append({"title":t,"url":lk,"source":"CoinTelegraph","ago":ago})
            except Exception: pass
            return self._s(200,"application/json",json.dumps(out))
        self._s(404,"text/plain","")
if __name__=="__main__":
    print("PUBLIC terminal http://0.0.0.0:8788"); ThreadingHTTPServer(("0.0.0.0",8788),H).serve_forever()
