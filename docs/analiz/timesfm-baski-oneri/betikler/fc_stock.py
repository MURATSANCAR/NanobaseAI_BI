"""Kesim tarihlerinde Logo stoku (STINVTOT: SUM(ONHAND) tarihe kadar) ve kesimden sonraki giriş (baskı) adetleri."""
import json, sys, time
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.profiler.connectors import connector_from_file
L = connector_from_file("/data/nanobaseai/bi/secrets/logo-mssql-connection.json"); L.query_timeout = 1200
# kesim ayının son günü, firma, ufuk sonu (giriş penceresi)
CUTS = [("2024-07", "2024-07-31", "211", "2025-07-31"), ("2025-01", "2025-01-31", "211", "2025-07-31"),
        ("2025-07", "2025-07-31", "211", "2025-12-31"), ("2026-01", "2026-01-31", "411", "2026-07-31"),
        ("simdi", "2026-08-17", "411", "2026-08-17")]
out = {}
for key, d, firm, end in CUTS:
    t = time.monotonic()
    _, rows, _ = L.execute(f"""SELECT i.CODE AS k,
        SUM(CASE WHEN s.DATE_ <= '{d}' THEN s.ONHAND ELSE 0 END) AS stok,
        SUM(CASE WHEN s.DATE_ > '{d}' AND s.DATE_ <= '{end}' THEN s.RECEIVED + s.ACTPRODIN ELSE 0 END) AS giris
      FROM dbo.LV_{firm}_01_STINVTOT AS s WITH (NOLOCK)
      JOIN dbo.LG_{firm}_ITEMS AS i WITH (NOLOCK) ON i.LOGICALREF = s.STOCKREF
      WHERE s.INVENNO <> -1
      GROUP BY i.CODE""", 500000)
    out[key] = {str(r["k"]).strip(): {"stok": float(r["stok"] or 0), "giris": float(r["giris"] or 0)} for r in rows}
    print(f"{key} ({firm}, {d}): {len(rows)} kod {time.monotonic()-t:.0f} sn", flush=True)
# 2026 kesiminde 2025 sonu devri: 211'deki 2025-12-31 stoku ile 411'in 2026-01-01 açılışı tutarlı mı
_, rows, _ = L.execute("""SELECT i.CODE AS k, SUM(s.ONHAND) AS stok FROM dbo.LV_211_01_STINVTOT s WITH (NOLOCK)
    JOIN dbo.LG_211_ITEMS i WITH (NOLOCK) ON i.LOGICALREF = s.STOCKREF WHERE s.INVENNO <> -1 AND s.DATE_ <= '2025-12-31' GROUP BY i.CODE""", 500000)
out["211_sonu"] = {str(r["k"]).strip(): {"stok": float(r["stok"] or 0)} for r in rows}
_, rows, _ = L.execute("""SELECT i.CODE AS k, SUM(s.ONHAND) AS stok FROM dbo.LV_411_01_STINVTOT s WITH (NOLOCK)
    JOIN dbo.LG_411_ITEMS i WITH (NOLOCK) ON i.LOGICALREF = s.STOCKREF WHERE s.INVENNO <> -1 AND s.DATE_ <= '2026-01-01' GROUP BY i.CODE""", 500000)
out["411_acilis"] = {str(r["k"]).strip(): {"stok": float(r["stok"] or 0)} for r in rows}
json.dump(out, open("/tmp/fc/stock.json", "w"))
print("BITTI", flush=True)
