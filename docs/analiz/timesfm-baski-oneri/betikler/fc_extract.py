"""Kitap başına aylık satış (2015–2026), Power BI'ın kaynağı V_SatisRaporu_ALL2 ile aynı satırlar (yıllık görünümler)."""
import json, sys, time
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.profiler.connectors import connector_from_file
L = connector_from_file("/data/nanobaseai/bi/secrets/logo-mssql-connection.json"); L.query_timeout = 900
C = connector_from_file("/data/nanobaseai/bi/secrets/crm-mssql-connection.json"); C.query_timeout = 300
monthly = {}
for y in range(2015, 2027):
    t = time.monotonic()
    _, rows, _ = L.execute(f"""SELECT [Malzeme/Hizmet Kodu] AS k, [Yıl] AS y, [Ay] AS m, SUM(Miktar) AS q, COUNT(*) AS n
        FROM dbo.V_SatisRaporu_{y} WHERE [Malzeme/Hizmet Kodu] NOT LIKE '157%' AND [KDVli Tutar] <> 0
        GROUP BY [Malzeme/Hizmet Kodu], [Yıl], [Ay]""", 2_000_000)
    for r in rows:
        monthly.setdefault(str(r["k"]).strip(), {})[f"{int(r['y'])}-{int(r['m']):02d}"] = float(r["q"] or 0)
    print(f"{y}: {len(rows)} kod-ay {time.monotonic()-t:.0f} sn", flush=True)
_, kitap, _ = C.execute(open("/data/nanobaseai/bi/frontend/backend/semantic_bridge/management/sql/baski_oneri/crm_kitap.sql", encoding="utf-8").read(), 100000)
_, yeni, _ = C.execute(open("/data/nanobaseai/bi/frontend/backend/semantic_bridge/management/sql/baski_oneri/crm_yeni_kitap.sql", encoding="utf-8").read(), 100000)
json.dump(monthly, open("/tmp/fc/monthly.json", "w"))
json.dump([{k: (str(v) if v is not None and not isinstance(v, (int, float, str)) else v) for k, v in r.items()} for r in kitap], open("/tmp/fc/kitap.json", "w"), ensure_ascii=False)
json.dump([{k: str(v) if v is not None else None for k, v in r.items()} for r in yeni], open("/tmp/fc/yeni.json", "w"), ensure_ascii=False)
print("BITTI kod:", len(monthly), "| kitap karti:", len(kitap), "| yeni:", len(yeni), flush=True)
