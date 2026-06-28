const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys')
const express = require('express'); const pino = require('pino'); const fs = require('fs')
const DIR = '/home/dnayaka/Documents/dynamic_rsi/btc-terminal/wa-daemon'
const PHONE = process.env.WA_PHONE || '6289672845575'
let sock = null, connected = false

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState(DIR + '/auth')
  let version; try { ({ version } = await fetchLatestBaileysVersion()) } catch (e) {}
  sock = makeWASocket({ version, auth: state, logger: pino({ level: 'silent' }), printQRInTerminal: false })
  sock.ev.on('creds.update', saveCreds)
  // PAIRING CODE (kalau belum terdaftar)
  if (!sock.authState.creds.registered) {
    setTimeout(async () => {
      try {
        const code = await sock.requestPairingCode(PHONE)
        const pretty = code.match(/.{1,4}/g).join('-')
        console.log('\n========================================')
        console.log('  PAIRING CODE: ' + pretty)
        console.log('========================================\n')
        fs.writeFileSync(DIR + '/pairing_code.txt', pretty)
      } catch (e) { console.log('pairing err', e.message) }
    }, 3000)
  }
  sock.ev.on('connection.update', (u) => {
    const { connection, lastDisconnect } = u
    if (connection === 'open') { connected = true; console.log('[WA] TERHUBUNG ✅'); try{fs.unlinkSync(DIR+'/pairing_code.txt')}catch(e){} }
    if (connection === 'close') {
      connected = false
      const code = lastDisconnect?.error?.output?.statusCode
      console.log('[WA] putus code', code)
      if (code !== DisconnectReason.loggedOut) setTimeout(start, 3000)
    }
  })
}
const app = express(); app.use(express.json())
app.get('/status', (req, res) => res.json({ connected }))
app.post('/send', async (req, res) => {
  try {
    if (!connected) return res.status(503).json({ ok: false, error: 'WA belum terhubung' })
    const jid = String(req.body.to).replace(/[^0-9]/g, '') + '@s.whatsapp.net'
    await sock.sendMessage(jid, { text: req.body.message }); res.json({ ok: true })
  } catch (e) { res.status(500).json({ ok: false, error: String(e) }) }
})
app.listen(18790, '127.0.0.1', () => console.log('[HTTP] listen 127.0.0.1:18790'))
start()
