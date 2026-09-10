---
nl: "Ağustos 2026 net satış tutarı nedir?"
sql: |
  SELECT SUM(CASE WHEN "TRCODE" IN (7,8,9) THEN "NETTOTAL" ELSE -"NETTOTAL" END) AS net_ciro FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0 AND "TRCODE" IN (2,3,7,8,9) AND "DATE_" >= '2026-08-01' AND "DATE_" < '2026-09-01'
source: imported
datasource: logo-tunnel
---
