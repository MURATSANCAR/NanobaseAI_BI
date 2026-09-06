---
nl: "En çok iade alan 10 müşteri kimler?"
sql: |
  SELECT c."CODE" AS cari_kodu, c."DEFINITION_" AS unvan, SUM(i."NETTOTAL") AS iade_tutari, COUNT(*) AS iade_faturasi FROM dbo_LG_411_01_INVOICE i JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF" WHERE i."CANCELLED" = 0 AND i."TRCODE" IN (2,3) GROUP BY c."CODE", c."DEFINITION_" ORDER BY iade_tutari DESC LIMIT 10
source: legacy-wren-ui
datasource: logo-tunnel
---
