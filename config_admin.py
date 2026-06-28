#!/usr/bin/env python3
"""PRIVATE ADMIN — kontrol trading (key/config/execute). LOCALHOST ONLY :8789. JANGAN expose ke publik."""
import json, os, requests, urllib3, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
urllib3.disable_warnings()
HERE="/home/dnayaka/Documents/dynamic_rsi/btc-terminal"; CFG=HERE+"/bot_config.json"; STATE=HERE+"/bot_v22_state.json"; SEC=HERE+"/bot_secrets.json"
S=requests.Session(); FAPI="https://fapi.binance.com"
def load():
    try: return json.load(open(CFG))
    except: return {"live":False,"size_usd":100,"leverage":1,"symbol":"BTC/USDT:USDT","sleeves":{"v20":True},"max_size_usd":2000}
def save(c): json.dump(c,open(CFG,"w"),indent=2)
def load_keys():
    try: s=json.load(open(SEC)); return s.get("key",""),s.get("secret","")
    except: return "",""
def place_market(side):
    c=load(); k,sec=load_keys()
    if not c.get("live",False): return {"ok":False,"msg":"Mode PAPER — aktifkan LIVE dulu utk order asli"}
    if not k or not sec: return {"ok":False,"msg":"API key belum diisi"}
    try:
        import ccxt
        price=float(S.get(FAPI+"/fapi/v1/ticker/price?symbol=BTCUSDT",timeout=10,verify=False).json()["price"])
        qty=round(c["size_usd"]*c["leverage"]/price,3); notional=qty*price
        if notional<100: return {"ok":False,"msg":f"${notional:.0f} < min $100"}
        ex=ccxt.binanceusdm({"apiKey":k,"secret":sec,"enableRateLimit":True,"options":{"defaultType":"future"}})
        try: ex.set_leverage(c["leverage"],c["symbol"])
        except: pass
        ex.create_order(c["symbol"],"market",side,qty)
        msg=f"FILLED {side.upper()} {qty} BTC ~${notional:.0f} @ {price:.0f}"
        try:
            from notify_wa import send_whatsapp; send_whatsapp("🖐️ "+msg)
        except: pass
        return {"ok":True,"msg":msg}
    except Exception as e: return {"ok":False,"msg":str(e)[:140]}
PAGE=r"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>ADMIN · v20</title>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@400..800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel=stylesheet>
<style>:root{--bg:#000;--panel:#070707;--ink:#e8e2d0;--dim:#8a7f63;--amber:#ff8c1a;--up:#27d07a;--down:#ff453a;--line:#1b1810;--mono:'IBM Plex Mono',monospace;--disp:'Bricolage Grotesque',sans-serif}
*{margin:0;padding:0;box-sizing:border-box}body{background:var(--bg);color:var(--ink);font-family:var(--mono);font-size:13px;max-width:520px;margin:0 auto;padding:18px}
.hd{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:16px}
.hd .b{font-family:var(--disp);font-weight:700;font-size:16px}.hd .b span{color:var(--down)}
a.back{color:var(--amber);text-decoration:none;font-size:11px;border:1px solid var(--line);padding:5px 10px;border-radius:4px}
.state{padding:4px 10px;border:1px solid var(--line);border-radius:3px;font-weight:600;font-size:11px;letter-spacing:.1em}
.state.live{color:var(--down);border-color:rgba(255,69,58,.5);box-shadow:0 0 14px rgba(255,69,58,.25)}.state.paper{color:var(--up)}
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
<div class=hd><div class=b>⚡ ADMIN<span>·</span>v20</div><div style="display:flex;gap:8px;align-items:center"><span class="state paper" id=state>PAPER</span><a class=back href="http://localhost:8788" target=_blank>terminal ↗</a></div></div>
<div class=px id=px>$—</div>
<div class=panel><h3>System · BTC v20</h3>
 <div class=switch><b id=livelbl>PAPER · safe</b><label class=phys><input type=checkbox id=live><span class=sl></span></label></div>
 <p class=warn>ON = bot AUTO trade uang asli.</p>
 <div class=field><div><label>Size USD</label><input class=inp type=number id=size></div><div><label>Leverage (max 1x)</label><input class=inp type=number id=lev min=1 max=1 value=1 title="Dikunci 1x (riset: WAJIB <=1x)"></div></div>
 <p class=warn id=not></p><button class=btn onclick=saveCfg()>Commit</button><div class=saved id=cs></div>
</div>
<div class=panel><h3>Manual Execute</h3>
 <div class=tbig><button class="tbtn buy" onclick="trade('buy')">▲ Long<span class=s>Market Buy</span></button><button class="tbtn sell" onclick="trade('sell')">▼ Short<span class=s>Market Sell</span></button></div>
 <div class=saved id=tmsg style="color:var(--dim);font-size:12px;margin-top:12px">size dari config di atas</div>
</div>
<div class=panel><h3>Position</h3><div id=pos></div></div>
<div class=panel><h3>API Credentials</h3><div class=keystat id=ks>—</div>
 <label>Key</label><input class=inp id=k placeholder="paste key"><label style=margin-top:9px>Secret</label><input class=inp id=s type=password placeholder="paste secret">
 <p class=warn>Futures · IP-restrict · NO withdraw · lokal chmod600</p><button class="btn ghost" onclick=saveKeys()>🔒 Store</button><div class=saved id=ksv></div>
</div>
<div class=toast id=toast></div><div class=modal id=modal><div class=box><h4>Konfirmasi Market Order</h4><div class=big id=mbig></div><p>Uang ASLI akan langsung dieksekusi di Binance futures.</p><div class=row><button class=cancel onclick=closeM()>Batal</button><button class=ok id=mok>Confirm</button></div></div></div><script>const $=id=>document.getElementById(id);
function fp(n){const d=n<100?2:0;return '$'+Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d})}
function px(){fetch('/api/metrics').then(r=>r.json()).then(m=>$('px').textContent=fp(m.mark))}
function cfg(){fetch('/api/config').then(r=>r.json()).then(c=>{$('live').checked=c.live;$('size').value=c.size_usd;$('lev').value=c.leverage;lv();nt()})}
function lv(){const on=$('live').checked;$('state').textContent=on?'● LIVE':'PAPER';$('state').className='state '+(on?'live':'paper');$('livelbl').textContent=on?'LIVE · uang asli':'PAPER · safe'}
function nt(){const n=(+$('size').value)*(+$('lev').value);$('not').textContent='Notional ~$'+n+(n<100?' · ⚠ < min $100':' · ✓')}
$('live').onchange=lv;$('size').oninput=nt;$('lev').oninput=nt;
function saveCfg(){fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({live:$('live').checked,size_usd:+$('size').value,leverage:+$('lev').value})}).then(r=>r.json()).then(_=>{$('cs').textContent='✓ committed';toast('Config tersimpan','ok');setTimeout(()=>$('cs').textContent='',2000)})}
function keyst(){fetch('/api/secrets').then(r=>r.json()).then(d=>$('ks').innerHTML=d.set?'<span style=color:var(--up)>● active ('+d.masked+')</span>':'<span style=color:var(--down)>○ no keys</span>')}
function saveKeys(){const k=$('k').value,s=$('s').value;if(!k||!s){alert('isi');return}fetch('/api/secrets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:k,secret:s})}).then(r=>r.json()).then(_=>{$('k').value='';$('s').value='';$('ksv').textContent='✓ stored';toast('API key tersimpan','ok');setTimeout(()=>$('ksv').textContent='',2000);keyst()})}
let pend=null;
function toast(m,t){const e=document.createElement('div');e.className='t '+(t||'');e.innerHTML='<span class=ic>'+(t=='ok'?'✓':t=='err'?'✕':'•')+'</span>'+m;$('toast').appendChild(e);setTimeout(()=>{e.classList.add('out');setTimeout(()=>e.remove(),300)},3800)}
function trade(side){const sz=$('size').value;pend=side;$('mbig').innerHTML='<span style="color:'+(side=='buy'?'var(--up)':'var(--down)')+'">'+(side=='buy'?'▲ LONG':'▼ SHORT')+' ~$'+sz+'</span>';$('mok').className='ok '+side;$('mok').textContent='Confirm '+(side=='buy'?'LONG':'SHORT');$('modal').classList.add('show')}
function closeM(){$('modal').classList.remove('show');pend=null}
function doTrade(){const side=pend;closeM();if(!side)return;$('tmsg').textContent='⟳ sending…';$('tmsg').style.color='var(--amber)';toast('Order '+side.toUpperCase()+' dikirim…','');fetch('/api/trade',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({side})}).then(r=>r.json()).then(d=>{$('tmsg').textContent=d.msg;$('tmsg').style.color=d.ok?'var(--up)':'var(--down)';toast(d.msg,d.ok?'ok':'err');setTimeout(pos,1500)})}
function pos(){fetch('/api/status').then(r=>r.json()).then(d=>{const s=d.sleeves.v20||{};const c=s.pos>0?'long':s.pos<0?'short':'flat';const t=s.pos>0?'LONG':s.pos<0?'SHORT':'FLAT';$('pos').innerHTML='<div class=pos><span class=nm>v20 <b class='+c+'>'+t+'</b>'+(s.pos?' @'+Math.round(s.entry):'')+'</span><span style=color:var(--dim)>×'+(s.equity||1).toFixed(3)+' · '+(s.ntr||0)+'t</span></div>'})}
$('mok').onclick=doTrade;px();cfg();keyst();pos();setInterval(px,15000);setInterval(pos,10000)
</script></body></html>"""
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _s(self,c,ct,b): self.send_response(c);self.send_header("Content-Type",ct);self.end_headers();self.wfile.write(b if isinstance(b,bytes) else b.encode())
    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/": return self._s(200,"text/html",PAGE)
        if path=="/api/config": return self._s(200,"application/json",json.dumps(load()))
        if path=="/api/metrics":
            d={"mark":0}
            try: d["mark"]=float(S.get(FAPI+"/fapi/v1/premiumIndex?symbol=BTCUSDT",timeout=8,verify=False).json()["markPrice"])
            except: pass
            return self._s(200,"application/json",json.dumps(d))
        if path=="/api/status":
            d={"sleeves":{}}
            try:
                st=json.load(open(STATE)); d["sleeves"]["v20"]=st.get("v20",{})
            except: pass
            return self._s(200,"application/json",json.dumps(d))
        if path=="/api/secrets":
            k,_=load_keys(); return self._s(200,"application/json",json.dumps({"set":bool(k),"masked":(k[:4]+"…"+k[-4:]) if len(k)>8 else ""}))
        self._s(404,"text/plain","")
    def do_POST(self):
        n=int(self.headers.get("Content-Length",0)); body=json.loads(self.rfile.read(n).decode()) if n else {}
        if self.path=="/api/config":
            c=load()
            if "live" in body: c["live"]=bool(body["live"])
            c["size_usd"]=max(1,min(c.get("max_size_usd",2000),int(body.get("size_usd",c["size_usd"]))))
            c["leverage"]=max(1,min(1,int(body.get("leverage",c["leverage"]))))   # HARD cap 1x (riset: WAJIB <=1x)
            save(c); return self._s(200,"application/json",'{"ok":true}')
        if self.path=="/api/secrets":
            json.dump({"key":body.get("key",""),"secret":body.get("secret","")},open(SEC,"w")); os.chmod(SEC,0o600)
            return self._s(200,"application/json",'{"ok":true}')
        if self.path=="/api/trade":
            return self._s(200,"application/json",json.dumps(place_market(body.get("side","buy"))))
        self._s(404,"text/plain","")
if __name__=="__main__":
    print("PRIVATE admin http://127.0.0.1:8789 (localhost only)")
    ThreadingHTTPServer(("127.0.0.1",8789),H).serve_forever()
