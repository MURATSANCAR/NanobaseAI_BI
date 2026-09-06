---
nl: "2026 iskonto oranı nedir?"
sql: |
  SELECT SUM(CASE WHEN "LINETYPE" = 0 THEN "TOTAL" ELSE 0 END) AS brut, SUM(CASE WHEN "LINETYPE" = 2 THEN "TOTAL" ELSE 0 END) AS iskonto, SUM(CASE WHEN "LINETYPE" = 2 THEN "TOTAL" ELSE 0 END) / NULLIF(SUM(CASE WHEN "LINETYPE" = 0 THEN "TOTAL" ELSE 0 END), 0) AS iskonto_orani FROM dbo_LG_411_01_STLINE WHERE "CANCELLED" = 0 AND "TRCODE" IN (7,8) AND "DATE_" >= '2026-01-01'
source: legacy-wren-ui
datasource: logo-tunnel
---
