"""Excel indirme kabulünü köprüyü süreç içinde kurarak koşturur (giriş servisine, oturum veritabanına dokunmadan).

Neden: kabul gerçek veriyle, bir kişinin yetkileriyle koşmalı; ama giriş oturumu açmak/oturum tablosuna satır eklemek
yerine kullanıcı çözümlemesi yalnız bu süreçte sabitlenir (`board._fetch_session`, pytest'teki `_app` ile aynı yol).
Sayfa kapısı, rol ve dışa aktarma yetkisi olduğu gibi işler.

Kayıt bırakmaz: dışa aktarma uçları denetim kaydı (`admin.audit`), erişim kaydı (`data_security.record_access`) ve İK
erişim kaydı (`hr_core.log_access`) yazar. Bu süreçte bu üç yazıcı sayaca bağlanır: çağrı sayılır ve kanıta yazılır,
veritabanına satır girmez (gerçek kullanımda aynı çağrılar yazılır; birim testleri ve canlı kayıt bunu gösterir).
Yaşam döngüsü (gece işleri, model kuyruğu) başlatılmaz: TestClient bağlam yöneticisi olmadan kullanılır.

Ortam: köprünün ortam dosyası (systemd-run -p EnvironmentFile=…), PYTHONPATH=<aday ağaç>/backend, TEST_USER (varsayılan
timasai). Kullanım: python yerinde.py [--out kanit.json] [--only …]
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Hazır cevap klasörü bu sürece ait geçici klasör: canlı köprünün klasörüne yazılmaz, açılışta orada biriken kayıtlar
# (bütün kişilerin) arkada yeniden üretilmeye çalışılmaz — 2026-09-29'da bu, test sürecini dakikalarca kilitledi.
import tempfile  # noqa: E402

os.environ["RESPONSE_CACHE_DIR"] = os.environ.get("KABUL_RC_DIR") or tempfile.mkdtemp(prefix="excel-kabul-rc-")

USER = os.environ.get("TEST_USER", "timasai")
COOKIE = "timas_session=excel-kabul-yerinde"
calls: Counter = Counter()

# 1) Kayıt yazıcıları — köprü kurulmadan önce (uçlar bunları kuruluşta referans olarak alır).
from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import data_security as ds_mod  # noqa: E402
from semantic_bridge import hr_core as hr_core_mod  # noqa: E402


def _audit(engine, actor, action, kind, object_id, title, detail=None):  # noqa: ANN001
    calls[f"denetim:{kind}"] += 1


def _access(engine, user, kind, method, path, perm_key=None, detail=None, at=None):  # noqa: ANN001
    calls[f"erisim:{kind}"] += 1


def _hr_access(*a, **k):  # noqa: ANN002, ANN003
    calls["ik-erisim"] += 1


admin_mod.audit = _audit
ds_mod.record_access = _access
hr_core_mod.log_access = _hr_access

# 2) Kişi: yalnız bu süreçte, yalnız bu çerezle.
from semantic_bridge import board as board_mod  # noqa: E402

board_mod._fetch_session = lambda cookie: {"username": USER, "displayName": USER} if COOKIE in (cookie or "") else None
board_mod._fetch_user = lambda cookie: USER if COOKIE in (cookie or "") else None

# 3) Köprü (modül yüklenirken create_app kurulur — yukarıdaki yamalarla).
from fastapi.testclient import TestClient  # noqa: E402

from semantic_bridge import app as app_mod  # noqa: E402

client = TestClient(app_mod.app, raise_server_exceptions=False)


def transport(path, headers, method, data):  # noqa: ANN001
    r = client.request(method, path, headers=headers, content=data)
    return r.status_code, dict(r.headers), r.content


import kabul as KB  # noqa: E402

KB.TRANSPORT = transport
KB.COOKIE = COOKIE
KB.COOKIE2 = ""
KB.CALLER = os.environ.get("SEMANTIC_CALLER_TOKEN", "")

if __name__ == "__main__":
    import atexit

    atexit.register(lambda: print("== kayıt çağrıları (yazılmadı): " + ", ".join(f"{k}={v}" for k, v in sorted(calls.items()))))
    KB.main()
