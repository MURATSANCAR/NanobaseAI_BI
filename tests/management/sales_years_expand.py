"""Yönetim raporları — `{satis:...}` yer tutucusunun yıllık Logo görünümlerine açılması (DB gerektirmez).

Koşturma (fastapi kurulu ortamda):  python3 tests/management/sales_years_expand.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from semantic_bridge.management import _values_rows, expand_sales, sales_years  # noqa: E402

sonuc = []


def ok(ad, kosul, gorulen=""):
    print(("GEÇTİ  " if kosul else "DÜŞTÜ  ") + ad + (f"   → {gorulen}" if gorulen else ""))
    sonuc.append(kosul)


EYLUL_26 = date(2026, 9, 23)
OCAK_27 = date(2027, 1, 2)

ok("sabit başlangıç: 2024 → 2024..2026", sales_years("2024", EYLUL_26) == [2024, 2025, 2026])
ok("göreli: -1 → geçen yıl + bu yıl", sales_years("-1", EYLUL_26) == [2025, 2026])
ok("yıl dönümünde kendiliğinden genişler: 2024 → 2024..2027", sales_years("2024", OCAK_27) == [2024, 2025, 2026, 2027])
ok("yıl dönümünde göreli kayar: -1 → 2026, 2027", sales_years("-1", OCAK_27) == [2026, 2027])

sql, missing = expand_sales("SELECT 1 FROM {satis:2024} AS s", EYLUL_26, {2024, 2025, 2026})
ok("üç kol, her biri kendi görünümünden", all(f"dbo.V_SatisRaporu_{y}" in sql for y in (2024, 2025, 2026)) and sql.count("UNION ALL") == 2)
ok("her kol ALL2'nin süzgecini taşır", sql.count("NOT LIKE '157%' AND [KDVli Tutar] <> 0") == 3)
ok("kolonlar adla seçilir (SELECT * yok)", "SELECT *" not in sql and "[Malzeme/Hizmet Kodu]" in sql)
ok("eksik yıl yok", missing == [])
ok("yer tutucu kalmadı", "{satis" not in sql)

sql, missing = expand_sales("FROM {satis:-1} AS s", OCAK_27, {2024, 2025, 2026})
ok("Ocak'ta 2027 görünümü henüz yoksa atlanır ve bildirilir", missing == [2027] and "V_SatisRaporu_2027" not in sql, str(missing))

try:
    expand_sales("FROM {satis:0} AS s", OCAK_27, {2025, 2026})
    ok("hiç görünüm yoksa hata verir (boş rapor üretmez)", False)
except RuntimeError as e:
    ok("hiç görünüm yoksa hata verir (boş rapor üretmez)", "görünümlerinin hiçbiri yok" in str(e), str(e))

sql, _ = expand_sales("-- yorum\nFROM {satis:-1} AS s  -- kuyruk yorumu\nWHERE 1=1", EYLUL_26, {2025, 2026})
satir = next(l for l in sql.splitlines() if "AS s" in l)
ok("satır sonu yorumu birleşimin kapanış parantezinden sonra kalır",
   satir.startswith(") AS s") and "-- kuyruk yorumu" in satir and sql.rstrip().endswith("WHERE 1=1"), satir)

ok("VALUES satırları: her kod ayrı satır, tek tırnak kaçışlı",
   _values_rows(["15201.01.001", "O'Neil"]) == "(N'15201.01.001'), (N'O''Neil')", _values_rows(["O'Neil"]))

ok("yıl yıl okuma: '2019-2019' → yalnız 2019", sales_years("2019-2019", EYLUL_26) == [2019])
sql, _ = expand_sales("FROM {satis:2019-2019} AS s", EYLUL_26, {2019, 2020})
ok("tek yıllık kol, birleşim yok", "V_SatisRaporu_2019" in sql and "UNION ALL" not in sql and "V_SatisRaporu_2020" not in sql)

print("SONUÇ:", f"{sum(sonuc)}/{len(sonuc)} geçti")
raise SystemExit(0 if all(sonuc) else 1)
