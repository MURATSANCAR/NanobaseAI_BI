---
nl: "Yayınevi bazında net ciro ve brüt kâr marjı nedir?"
sql: |
  SELECT COALESCE(NULLIF(it."SPECODE", ''), '(boş)') AS yayinevi, SUM(CASE WHEN sl."TRCODE" IN (7,8) THEN sl."TOTAL" ELSE -sl."TOTAL" END) AS net_ciro, 1 - SUM(CASE WHEN sl."TRCODE" IN (7,8) AND sl."OUTCOST" <> 0 THEN sl."AMOUNT" * sl."OUTCOST" ELSE 0 END) / NULLIF(SUM(CASE WHEN sl."TRCODE" IN (7,8) AND sl."OUTCOST" <> 0 THEN sl."TOTAL" ELSE 0 END), 0) AS brut_kar_marji FROM dbo_LG_411_01_STLINE sl JOIN dbo_LG_411_ITEMS it ON it."LOGICALREF" = sl."STOCKREF" WHERE sl."CANCELLED" = 0 AND sl."LINETYPE" = 0 AND sl."TRCODE" IN (2,3,7,8) GROUP BY 1 ORDER BY net_ciro DESC
source: legacy-wren-ui
datasource: logo-tunnel
---
