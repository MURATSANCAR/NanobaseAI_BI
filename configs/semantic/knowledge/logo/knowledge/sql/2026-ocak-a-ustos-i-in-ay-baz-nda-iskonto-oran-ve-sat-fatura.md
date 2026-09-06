---
nl: 2026 Ocak–Ağustos için ay bazında iskonto oranı ve satış faturası başına ortalama
  fatura tutarı
sql: "WITH iskonto AS (\n  SELECT DATEFROMPARTS(YEAR(\"DATE_\"), MONTH(\"DATE_\"),\
  \ 1) AS ay,\n         SUM(CASE WHEN \"LINETYPE\" = 2 THEN \"TOTAL\" ELSE 0 END)\
  \ / NULLIF(SUM(CASE WHEN \"LINETYPE\" = 0 THEN \"TOTAL\" ELSE 0 END), 0) AS iskonto_orani\n\
  \  FROM dbo_LG_411_01_STLINE WHERE \"CANCELLED\" = 0 AND \"TRCODE\" IN (7,8) AND\
  \ \"DATE_\" >= '2026-01-01' AND \"DATE_\" < '2026-09-01'\n  GROUP BY DATEFROMPARTS(YEAR(\"\
  DATE_\"), MONTH(\"DATE_\"), 1)\n), fatura AS (\n  SELECT DATEFROMPARTS(YEAR(\"DATE_\"\
  ), MONTH(\"DATE_\"), 1) AS ay, AVG(\"NETTOTAL\") AS ortalama_fatura_tutari, COUNT(*)\
  \ AS fatura_sayisi\n  FROM dbo_LG_411_01_INVOICE WHERE \"CANCELLED\" = 0 AND \"\
  TRCODE\" IN (7,8,9) AND \"DATE_\" >= '2026-01-01' AND \"DATE_\" < '2026-09-01'\n\
  \  GROUP BY DATEFROMPARTS(YEAR(\"DATE_\"), MONTH(\"DATE_\"), 1)\n)\nSELECT i.ay,\
  \ i.iskonto_orani, f.ortalama_fatura_tutari, f.fatura_sayisi\nFROM iskonto i JOIN\
  \ fatura f ON f.ay = i.ay ORDER BY i.ay"
source: verified-2026-09-06
created_at: '2026-09-06T06:41:10.363569+00:00'
datasource: logo-tunnel
---
