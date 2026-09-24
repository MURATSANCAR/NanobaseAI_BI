"""Yönetim raporları — her rapor kendi veritabanı bağlantısını kullanır (DB gerektirmez).

İki rapor (Baskı Öneri ve ZEKI AI tahmini) ayrı iş parçacıklarında aynı anda yenilenir; pyodbc bağlantısı
paylaşılırsa "Invalid cursor state" (2026-09-24). Koşturma:  python3 tests/management/report_connections.py
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
fake = types.ModuleType("semantic_layer.profiler.connectors")
made = []


class Conn:
    query_timeout = 0


def connector_from_file(path):
    c = Conn(); made.append(c); return c


fake.connector_from_file = connector_from_file
sys.modules.setdefault("semantic_layer", types.ModuleType("semantic_layer"))
sys.modules.setdefault("semantic_layer.profiler", types.ModuleType("semantic_layer.profiler"))
sys.modules["semantic_layer.profiler.connectors"] = fake
from semantic_bridge.management import Reports  # noqa: E402

r = Reports(lambda: {"logo": __file__, "crm": __file__})
a1, a2 = r._connector("logo", "baski-oneri"), r._connector("logo", "baski-oneri")
b1 = r._connector("logo", "baski-oneri-tahmin")
sonuc = [a1 is a2, a1 is not b1, len(made) == 2]
print(("GEÇTİ " if sonuc[0] else "DÜŞTÜ ") + " aynı rapor aynı bağlantıyı yeniden kullanır")
print(("GEÇTİ " if sonuc[1] else "DÜŞTÜ ") + " iki rapor ayrı bağlantı kullanır")
print(("GEÇTİ " if sonuc[2] else "DÜŞTÜ ") + " iki rapor için tam iki bağlantı açılır")
print("SONUÇ:", f"{sum(sonuc)}/{len(sonuc)} geçti")
raise SystemExit(0 if all(sonuc) else 1)
