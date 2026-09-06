---
nl: 2026 toplam net ciro nedir?
sql: SELECT SUM(CASE WHEN "TRCODE" IN (7,8,9) THEN "NETTOTAL" ELSE -"NETTOTAL" END)
  AS net_ciro FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0 AND "TRCODE" IN (2,3,7,8,9)
  AND "DATE_" >= '2026-01-01' AND "DATE_" < '2027-01-01'
source: user
created_at: '2026-09-06T06:49:56.283707+00:00'
---
