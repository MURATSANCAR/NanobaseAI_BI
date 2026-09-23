"""Editoryal ön ısıtma: liste ekranlarının açılış görünümleri kaydedilir, 5 dk'lık turda yeniden okunur.

Veritabanı gerekmez; kurucular ve ısıtıcılar sayaçtır. Koşturma:  python3 tests/editorial/home_views_warm.py
"""
import importlib.util
import json
import os
import tempfile
import time
from pathlib import Path

os.environ["EDITORIAL_HOME_CACHE_DIR"] = tempfile.mkdtemp()
_spec = importlib.util.spec_from_file_location(
    "editorial_home", Path(__file__).resolve().parents[2] / "backend/semantic_bridge/editorial_home.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

calls = {"summary": 0, "contracts": []}
builders = {"summary": lambda: calls.__setitem__("summary", calls["summary"] + 1) or {"n": calls["summary"]}}
warmers = {"contracts": lambda **kw: calls["contracts"].append(kw)}
snap = m.EditorialHomeSnapshots(lambda: ["t", "d"], lambda: builders, lambda: warmers)

# 1) Açılış görünümü kaydedilir ve ilk turda okunur.
snap.remember("contracts", {"order": "bitis", "q": ""})
snap.refresh()
assert calls["summary"] == 1, calls
assert calls["contracts"] == [{"order": "bitis", "q": ""}], calls

# 2) 5 dk dolmadan ikinci tur koşmaz.
snap.refresh()
assert calls["summary"] == 1 and len(calls["contracts"]) == 1, calls

# 3) Düğme (force) aralığı beklemez; yalnız özetleri yeniler, liste ısıtması o istekte beklenmez.
snap.refresh(force=True)
assert calls["summary"] == 2 and len(calls["contracts"]) == 1, calls
assert snap.read()["parts"]["summary"]["data"] == {"n": 2}

# 4) Bir gün istenmeyen görünüm turdan düşer.
views_path = snap.directory() / "views.json"
views = json.loads(views_path.read_text())
for v in views.values():
    v["askedAt"] = time.time() - m.VIEW_IDLE - 1
views_path.write_text(json.dumps(views))
snap.warm(snap.directory())
assert len(calls["contracts"]) == 1, calls
assert json.loads(views_path.read_text()) == {}

# 5) Bilinmeyen ya da hata veren ısıtıcı turu düşürmez.
warmers["contracts"] = lambda **kw: (_ for _ in ()).throw(RuntimeError("CRM kapalı"))
snap.remember("contracts", {"q": ""})
snap.remember("yok", {"q": ""})
snap.warm(snap.directory())

print("home_views_warm: 5/5 geçti")
