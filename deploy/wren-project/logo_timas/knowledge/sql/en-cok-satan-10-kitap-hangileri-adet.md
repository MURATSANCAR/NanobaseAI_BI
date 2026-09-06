---
nl: "En çok satan 10 kitap hangileri (adet)?"
sql: |
  SELECT it."CODE" AS stok_kodu, it."NAME" AS kitap, SUM(sl."AMOUNT") AS adet, SUM(sl."TOTAL") AS tutar FROM dbo_LG_411_01_STLINE sl JOIN dbo_LG_411_ITEMS it ON it."LOGICALREF" = sl."STOCKREF" WHERE sl."CANCELLED" = 0 AND sl."LINETYPE" = 0 AND sl."TRCODE" IN (7,8) GROUP BY it."CODE", it."NAME" ORDER BY adet DESC LIMIT 10
source: legacy-wren-ui
datasource: logo-tunnel
---
