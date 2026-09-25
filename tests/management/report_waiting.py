"""Yönetim raporları — bağımlı rapor hazır değilken tahmin 'hata' değil 'bekliyor' kaydeder (DB gerektirmez).

2026-09-25: VM'de konteyner yenilenince tahmin raporu Baskı Öneri'den önce başlayıp düşüyor, 30 dk bekliyordu.
Koşturma:  python3 tests/management/report_waiting.py
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

tmp = tempfile.mkdtemp()
os.environ["MANAGEMENT_REPORT_CACHE_DIR"] = tmp
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
fake = types.ModuleType("semantic_layer.profiler.connectors")
fake.connector_from_file = lambda path: None
sys.modules.setdefault("semantic_layer", types.ModuleType("semantic_layer"))
sys.modules.setdefault("semantic_layer.profiler", types.ModuleType("semantic_layer.profiler"))
sys.modules["semantic_layer.profiler.connectors"] = fake
import semantic_bridge.management as mg  # noqa: E402
from semantic_bridge.management import zeki_tahmin as zt  # noqa: E402

sonuc = []


def ok(ad, kosul, gorulen=""):
    print(("GEÇTİ  " if kosul else "DÜŞTÜ  ") + ad + (f"   → {gorulen}" if gorulen else ""))
    sonuc.append(kosul)


try:
    zt.build(lambda *a: {}, inputs={}, post=lambda p: {}, ready=lambda: None); raised = None
except Exception as e:  # noqa: BLE001
    raised = e
ok("Baskı Öneri verisi yokken tahmin 'bekliyor' istisnası atar", getattr(raised, "waiting", False), repr(raised))

r = mg.Reports(lambda: {"logo": __file__, "crm": __file__})
r.path(zt.REPORT_ID).parent.mkdir(parents=True, exist_ok=True)
orig_ready = zt.service_ready
zt.service_ready = lambda: None  # uzak servis sorulmaz
build_defaults = list(zt.build.__defaults__); build_defaults[-1] = lambda: None; zt.build.__defaults__ = tuple(build_defaults)
r.refresh(zt.REPORT_ID)
snap = json.loads(r.path(zt.REPORT_ID).read_text())
ok("önbellekte hata yok, bekleme kaydı var", not snap.get("error") and snap.get("waitingAt") and "bekleniyor" in snap.get("waiting", ""),
   str({k: snap.get(k) for k in ("error", "waiting", "failedAt")}))
due = mg._next_due(snap, mg.interval_of(zt))
ok("bir sonraki deneme 1 dk sonra (30 dk değil)", abs(due - (snap["waitingAt"] + mg.MIN_GAP_SECONDS)) < 1e-6)
empty = zt.empty_text(None)
ok("beklerken sekme 'hazırlanıyor' der", "hazırlanıyor" in empty)

print("SONUÇ:", f"{sum(sonuc)}/{len(sonuc)} geçti")
raise SystemExit(0 if all(sonuc) else 1)
