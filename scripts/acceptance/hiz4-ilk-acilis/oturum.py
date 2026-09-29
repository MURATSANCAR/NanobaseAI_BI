"""timasai için 15 dakikalık kısa oturum açar (`ac`) ya da açtığını siler (`sil <çerez>`). sudo ile koşar.

Giriş servisinin oturum tablosu `/var/lib/timas-login/sessions.sqlite` (token = sha256(çerez)). Yeni kullanıcı adı
uydurulmaz; yalnız timasai (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»). Çerez ekrana/günlüğe yazılmaz:
`ac` çıktısı dosyaya yönlendirilir (600), iş bitince `sil` ile satır silinir.
"""
import hashlib
import secrets
import sqlite3
import sys
import time

DB = "/var/lib/timas-login/sessions.sqlite"
c = sqlite3.connect(DB)
if sys.argv[1] == "ac":
    raw = secrets.token_urlsafe(32)
    c.execute("INSERT INTO sessions (token, username, expires, display) VALUES (?, ?, ?, ?)",
              (hashlib.sha256(raw.encode()).hexdigest(), "timasai", time.time() + 900, "timasai"))
    c.commit()
    print(raw)
else:
    n = c.execute("DELETE FROM sessions WHERE token = ?", (hashlib.sha256(sys.argv[2].encode()).hexdigest(),)).rowcount
    c.commit()
    print(f"silindi: {n}")
