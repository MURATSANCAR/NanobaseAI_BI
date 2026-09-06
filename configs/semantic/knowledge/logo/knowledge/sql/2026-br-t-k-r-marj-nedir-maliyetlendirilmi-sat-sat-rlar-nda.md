---
nl: 2026 brüt kâr marjı nedir (maliyetlendirilmiş satış satırlarında)
sql: SELECT 1 - SUM(CASE WHEN "LINETYPE" = 0 AND "OUTCOST" <> 0 THEN "AMOUNT" * "OUTCOST"
  ELSE 0 END) / NULLIF(SUM(CASE WHEN "LINETYPE" = 0 AND "OUTCOST" <> 0 THEN "TOTAL"
  ELSE 0 END), 0) AS brut_kar_marji FROM dbo_LG_411_01_STLINE WHERE "CANCELLED" =
  0 AND "TRCODE" IN (7,8) AND "DATE_" >= '2026-01-01' AND "DATE_" < '2027-01-01'
source: user
tags:
- source:enrich
---
