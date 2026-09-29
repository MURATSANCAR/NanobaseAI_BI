"""M10 ön çalışma: ilk baskı raporunun kaynaklarını (repo SQL'leri, aynı genişletme) gerçek DB'den okuyup saklar.
Salt okuma. Koşturma: python extract.py  → /tmp/claude-m10/data.json.z (türleri koruyan JSON + zlib; pickle değil: okunurken kod
çalıştırmaz)"""
import sys
import time
from datetime import date

sys.path.insert(0, "/tmp/claude-m10/stage")
sys.path.insert(1, "/data/nanobaseai/bi/frontend/backend")
from semantic_bridge.management import Reports, sql_text  # noqa: E402
from semantic_bridge.management import ilk_baski  # noqa: E402
from semantic_bridge import typed_json as TJ  # noqa: E402

files = {"logo": "/data/nanobaseai/bi/secrets/logo-mssql-connection.json",
         "crm": "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"}
rep = Reports(lambda: files)
ctx: dict = {}
out = {}
for sid in ("crm_kitaplar", "crm_emsal", "logo_son_fatura"):
    t = time.time()
    out[sid] = rep._run(ilk_baski, sid, None, ctx)
    print(sid, len(out[sid]["records"]), f"{time.time() - t:.0f} sn", flush=True)
sales = []
for y in range(2015, date.today().year + 1):
    t = time.time()
    r = rep._run(ilk_baski, "logo_aylik_kanal", {"yil": y}, ctx)
    sales += r["records"]
    print("satis", y, len(r["records"]), f"{time.time() - t:.0f} sn", r.get("warning") or "", flush=True)
out["logo_aylik_kanal"] = {"records": sales}
with open("/tmp/claude-m10/data.json.z", "wb") as f:
    f.write(TJ.pack(out))
print("bitti", flush=True)
