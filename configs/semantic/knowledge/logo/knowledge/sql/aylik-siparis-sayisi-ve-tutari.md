---
nl: "2026 ay bazında açılan sipariş sayısı ve toplam sipariş tutarı (sipariş fişleri)"
sql: |
  SELECT DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay,
         COUNT(DISTINCT "LOGICALREF") AS siparis_sayisi,
         SUM("NETTOTAL") AS toplam_tutar
  FROM dbo_LG_411_01_ORFICHE
  WHERE "CANCELLED" = 0 AND "DATE_" >= '2026-01-01' AND "DATE_" < '2027-01-01'
  GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)
  ORDER BY ay
source: verified-2026-09-06
datasource: logo-tunnel
---
