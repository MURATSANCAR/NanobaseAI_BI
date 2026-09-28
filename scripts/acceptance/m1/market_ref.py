"""Bağımsız referans: bir kitaplığın kohort ilk yıl net satışı ve son 36 ay kanal toplamı, doğrudan DB'den.
Uygulamadan farklı yol: ilk yıl penceresi ve iade işareti SQL tarafında hesaplanır; çeyrekler statistics ile."""
import sys, json, time, statistics
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.profiler.connectors import connector_from_file

crm = connector_from_file("/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
logo = connector_from_file("/data/nanobaseai/bi/secrets/logo-mssql-connection.json")
crm.query_timeout = logo.query_timeout = 900
cat = sys.argv[1]  # kitaplık adı

t = time.time()
_, rows, _ = crm.execute(
    "DECLARE @m0 date = DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1); "
    "SELECT LTRIM(RTRIM(k.new_StokKodu)) AS kod, MIN(CAST(k.new_ilkyayintarihi AS date)) AS ilk "
    "FROM dbo.new_kitapBase k JOIN dbo.new_kitaplikBase kl ON kl.new_kitaplikId = k.new_kitaplikid "
    f"WHERE kl.new_name = N'{cat}' AND k.statecode = 0 AND LTRIM(RTRIM(ISNULL(k.new_StokKodu,''))) <> '' "
    "AND k.new_ilkyayintarihi >= DATEADD(month, -48, @m0) AND k.new_ilkyayintarihi < DATEADD(month, -12, @m0) "
    "GROUP BY LTRIM(RTRIM(k.new_StokKodu))", 100000)
print("kohort", len(rows), "kitap", round(time.time() - t, 1), "sn")
idx = {r["kod"]: (r["ilk"].year * 12 + r["ilk"].month - 1) if hasattr(r["ilk"], "year") else None for r in rows}
vals = ", ".join("(N'%s', %d)" % (k.replace("'", "''"), v) for k, v in idx.items() if v is not None)
now = time.localtime()
now_i = now.tm_year * 12 + now.tm_mon - 1
first = {k: 0.0 for k in idx}
lines = {k: 0 for k in idx}
chan = {}
years = range(min(v for v in idx.values()) // 12, now.tm_year + 1)
for y in years:
    t = time.time()
    sql = ("SELECT s.[Malzeme/Hizmet Kodu] AS kod, s.KANAL AS kanal, COUNT(*) AS n, "
           "SUM(CASE WHEN (s.[Yıl]*12 + s.[Ay] - 1) - c.i BETWEEN 0 AND 11 THEN "
           "  CASE WHEN UPPER(s.Satis_Iade) LIKE N'%ADE%' THEN -ABS(s.Miktar) ELSE s.Miktar END ELSE 0 END) AS ilk_yil, "
           f"SUM(CASE WHEN (s.[Yıl]*12 + s.[Ay] - 1) BETWEEN {now_i - 35} AND {now_i} THEN "
           "  CASE WHEN UPPER(s.Satis_Iade) LIKE N'%ADE%' THEN -ABS(s.Miktar) ELSE s.Miktar END ELSE 0 END) AS son36 "
           f"FROM dbo.V_SatisRaporu_{y} s JOIN (VALUES {vals}) AS c(k, i) ON c.k = s.[Malzeme/Hizmet Kodu] "
           "WHERE s.[Malzeme/Hizmet Kodu] NOT LIKE '157%' AND s.[KDVli Tutar] <> 0 "
           "GROUP BY s.[Malzeme/Hizmet Kodu], s.KANAL")
    try:
        _, r2, _ = logo.execute(sql, 1000000)
    except Exception as e:
        print(y, "HATA", str(e)[:200]); continue
    for r in r2:
        first[r["kod"]] += float(r["ilk_yil"] or 0)
        lines[r["kod"]] += int(r["n"] or 0)
        name = (r["kanal"] or "").strip() or "Belirtilmemiş"
        chan[name] = chan.get(name, 0.0) + float(r["son36"] or 0)
    print(y, len(r2), "satır", round(time.time() - t, 1), "sn")
sold = [first[k] for k in idx if lines[k] > 0]
q = statistics.quantiles(sold, n=4, method="inclusive") if len(sold) >= 2 else [None] * 3
print(json.dumps({"books": len(idx), "withSales": len(sold), "p25": round(q[0]) if q[0] is not None else None,
                  "p50": round(statistics.median(sold)) if sold else None, "p75": round(q[2]) if q[2] is not None else None,
                  "channels": {k: round(v) for k, v in sorted(chan.items(), key=lambda kv: -kv[1])},
                  "last36": round(sum(chan.values()))}, ensure_ascii=False))
