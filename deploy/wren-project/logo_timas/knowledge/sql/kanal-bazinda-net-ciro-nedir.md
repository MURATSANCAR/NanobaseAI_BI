---
nl: "Kanal bazında net ciro nedir?"
sql: |
  SELECT COALESCE(NULLIF(c."SPECODE2", ''), '(boş)') AS kanal, SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" ELSE -i."NETTOTAL" END) AS net_ciro, COUNT(DISTINCT i."CLIENTREF") AS cari_sayisi FROM dbo_LG_411_01_INVOICE i JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF" WHERE i."CANCELLED" = 0 AND i."TRCODE" IN (2,3,7,8,9) GROUP BY 1 ORDER BY net_ciro DESC
source: legacy-wren-ui
datasource: logo-tunnel
---
