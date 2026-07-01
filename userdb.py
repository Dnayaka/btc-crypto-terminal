#!/usr/bin/env python3
"""userdb.py — shared user/session store (server-side JSON, chmod 600, tak ter-scrape).
Dipakai config_server.py (login publik :8788) + config_admin.py (kelola user :8789).
Fitur: scrypt hash, session cookie, akun TRIAL (expires per-hari), admin flag."""
import json, os, hashlib, secrets, hmac as _hmac, threading, time as _time
HERE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_F  = HERE_DIR + "/users.json"
SESS_F   = HERE_DIR + "/sessions.json"
_LK = threading.Lock()
SESS_TTL = 30 * 86400   # cookie 30 hari (terpisah dari trial-expiry akun)

def _hash_pw(pw, salt): return hashlib.scrypt(pw.encode(), salt=salt, n=16384, r=8, p=1, dklen=32).hex()
def _jload(fp, d):
    try:
        with open(fp) as f: return json.load(f)
    except Exception: return d
def _jsave(fp, obj):
    tmp = fp + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # 600 dari awal -> tak world-readable
    with os.fdopen(fd, "w") as f: json.dump(obj, f)
    os.replace(tmp, fp)

# ---------- users ----------
def load_users():
    with _LK: return _jload(USERS_F, {})
def add_user(username, pw, admin=False, days=0):
    """days>0 -> akun TRIAL (kadaluarsa now+days*24h). days<=0 -> permanen."""
    username = (username or "").strip()
    if not username or not pw: return False
    try: days = max(0, int(days or 0))
    except Exception: days = 0
    with _LK:
        u = _jload(USERS_F, {}); salt = secrets.token_bytes(16); now = int(_time.time())
        u[username] = {"salt": salt.hex(), "hash": _hash_pw(pw, salt), "admin": bool(admin),
                       "created": now, "expires": (now + days * 86400) if days > 0 else 0,
                       "trial": days > 0}
        _jsave(USERS_F, u); return True
def del_user(username):
    with _LK:
        u = _jload(USERS_F, {})
        if username in u: del u[username]; _jsave(USERS_F, u); return True
    return False
def set_expiry(username, days):
    """Ubah masa-aktif akun (days>0 trial, days<=0 permanen)."""
    try: days = int(days)
    except Exception: return False
    with _LK:
        u = _jload(USERS_F, {})
        if username not in u: return False
        now = int(_time.time())
        u[username]["expires"] = (now + days * 86400) if days > 0 else 0
        u[username]["trial"] = days > 0
        _jsave(USERS_F, u); return True
def is_expired(username):
    v = load_users().get(username)
    if not v: return False
    e = v.get("expires", 0)
    return bool(e) and _time.time() > e
def is_admin(username): return bool(load_users().get(username, {}).get("admin"))
def verify_user(username, pw):
    """True hanya kalau password cocok DAN akun belum kadaluarsa."""
    u = load_users().get(username)
    if not u: return False
    e = u.get("expires", 0)
    if e and _time.time() > e: return False   # trial habis -> tolak login
    try: return _hmac.compare_digest(_hash_pw(pw, bytes.fromhex(u["salt"])), u["hash"])
    except Exception: return False
def list_users():
    out = []; now = int(_time.time())
    for k, v in load_users().items():
        e = v.get("expires", 0)
        out.append({"u": k, "admin": bool(v.get("admin")), "trial": bool(v.get("trial")),
                    "created": v.get("created", 0), "expires": e,
                    "expired": bool(e) and now > e,
                    "days_left": (max(0, (e - now)) // 86400) if e else None})
    return sorted(out, key=lambda x: (not x["admin"], x["u"]))

# ---------- sessions ----------
def make_session(user):
    with _LK:
        s = _jload(SESS_F, {}); now = int(_time.time())
        s = {k: v for k, v in s.items() if v.get("exp", 0) > now}   # prune kadaluarsa
        tok = secrets.token_urlsafe(32); s[tok] = {"user": user, "exp": now + SESS_TTL}
        _jsave(SESS_F, s); return tok
def session_user(tok):
    """Kembalikan username kalau session valid DAN akun masih ada & belum trial-expired."""
    if not tok: return None
    s = _jload(SESS_F, {}); v = s.get(tok)
    if not (v and v.get("exp", 0) > int(_time.time())): return None
    user = v.get("user"); u = load_users().get(user)
    if not u: return None
    e = u.get("expires", 0)
    if e and _time.time() > e: return None   # trial habis -> session mati
    return user
def del_session(tok):
    if not tok: return
    with _LK:
        s = _jload(SESS_F, {})
        if tok in s: del s[tok]; _jsave(SESS_F, s)

def bootstrap_admin(username, pw):
    """Buat admin pertama kalau users.json kosong."""
    if not load_users() and pw:
        add_user(username, pw, admin=True)
        return True
    return False
