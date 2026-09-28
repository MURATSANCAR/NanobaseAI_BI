"""M49 kabulünün bıraktığı test satırlarını siler (kullanıcı kuralı: test verisi bırakılmaz). Kabul başlangıcından
(`--t0` ya da `--out` dosyasındaki t0) sonra yazılan:
- `semantic_security_logins`: timasai (ve `--users` ile verilen ikinci oturumun hesabı) satırları,
- `semantic_security_access`: bu hesapların 403 satırları ve `/kabul` dışa aktarma bildirimi,
- `semantic_security_alerts`: bu hesaplar için açılmış «hatalı giriş» uyarısı,
- `semantic_audit`: bu hesapların `session` / `security_alert` kayıtları.
Giriş servisinin SQLite'ındaki olay ve oturum satırları `check.sh` içinde sudo ile silinir (bu betik o dosyaya yazamaz).
Önce `--dry` ile sayılar gösterilir; silinen sayılar günlüğe yazılır.

Kullanım: cleanup.py --out /tmp/claude-m49/kabul.json [--users timasai,ikinci] [--dry]
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.environ.get("M49_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="")
ap.add_argument("--t0", default="")
ap.add_argument("--users", default="timasai")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
t0 = datetime.fromisoformat(a.t0 or json.load(open(a.out))["t0"])
users = [u.strip().lower() for u in a.users.split(",") if u.strip()]
eng = sa.create_engine(SemanticSettings.from_env().store_dsn)
steps = [
    ("giriş kaydı", "DELETE FROM semantic_security_logins WHERE at > :t AND username = ANY(:u)",
     "SELECT count(*) FROM semantic_security_logins WHERE at > :t AND username = ANY(:u)"),
    ("erişim kaydı", "DELETE FROM semantic_security_access WHERE at > :t AND (username = ANY(:u) OR path = '/kabul')",
     "SELECT count(*) FROM semantic_security_access WHERE at > :t AND (username = ANY(:u) OR path = '/kabul')"),
    ("uyarı", "DELETE FROM semantic_security_alerts WHERE at > :t AND rule = 'hatali_giris' AND username = ANY(:u)",
     "SELECT count(*) FROM semantic_security_alerts WHERE at > :t AND rule = 'hatali_giris' AND username = ANY(:u)"),
    ("değişiklik kaydı", "DELETE FROM semantic_audit WHERE at > :t AND actor = ANY(:u) AND kind IN ('session', 'security_alert')",
     "SELECT count(*) FROM semantic_audit WHERE at > :t AND actor = ANY(:u) AND kind IN ('session', 'security_alert')"),
]
counts = {}
with eng.begin() as c:
    for name, delete, count in steps:
        counts[name] = c.execute(sa.text(count), {"t": t0, "u": users}).scalar()
        if not a.dry:
            c.execute(sa.text(delete), {"t": t0, "u": users})
print("silinecek" if a.dry else "silinen", counts, "hesaplar:", users, "t0:", t0.isoformat())
