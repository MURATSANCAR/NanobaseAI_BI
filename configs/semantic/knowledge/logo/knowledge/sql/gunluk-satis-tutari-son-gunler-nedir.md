---
nl: "Günlük satış tutarı (son günler) nedir?"
sql: |
  SELECT CAST("DATE_" AS DATE) AS gun, SUM("NETTOTAL") AS satis FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0 AND "TRCODE" IN (7,8,9) AND "DATE_" >= '2026-08-01' GROUP BY CAST("DATE_" AS DATE) ORDER BY 1
source: imported
datasource: logo-tunnel
---
