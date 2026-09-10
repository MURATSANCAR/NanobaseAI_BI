---
nl: 2026 yılında KITAPCI, E-TICARET ve DAGITICI kanalları için ay bazında net ciro
  (satış eksi iade) ve her kanalın o ay içindeki payını yüzde olarak ver; ay ve kanal
  sırasıyla listele.
sql: "SELECT \n    DATEFROMPARTS(YEAR(i.\"DATE_\"), MONTH(i.\"DATE_\"), 1) AS ay,\n\
  \    COALESCE(NULLIF(c.\"SPECODE2\", ''), '(boş)') AS kanal,\n    SUM(CASE WHEN\
  \ i.\"TRCODE\" IN (7,8,9) THEN i.\"NETTOTAL\" ELSE -i.\"NETTOTAL\" END) AS net_ciro,\n\
  \    SUM(CASE WHEN i.\"TRCODE\" IN (7,8,9) THEN i.\"NETTOTAL\" ELSE -i.\"NETTOTAL\"\
  \ END) * 100.0 / NULLIF(SUM(SUM(CASE WHEN i.\"TRCODE\" IN (7,8,9) THEN i.\"NETTOTAL\"\
  \ ELSE -i.\"NETTOTAL\" END)) OVER (PARTITION BY DATEFROMPARTS(YEAR(i.\"DATE_\"),\
  \ MONTH(i.\"DATE_\"), 1)), 0) AS kanal_payi_yuzde\nFROM dbo_LG_411_01_INVOICE i\n\
  JOIN dbo_LG_411_CLCARD c ON c.\"LOGICALREF\" = i.\"CLIENTREF\"\nWHERE i.\"CANCELLED\"\
  \ = 0\n  AND i.\"TRCODE\" IN (2,3,7,8,9)\n  AND i.\"DATE_\" >= '2026-01-01'\n  AND\
  \ i.\"DATE_\" < '2027-01-01'\n  AND c.\"SPECODE2\" IN ('KITAPCI', 'E-TICARET', 'DAGITICI')\n\
  GROUP BY \n    DATEFROMPARTS(YEAR(i.\"DATE_\"), MONTH(i.\"DATE_\"), 1),\n    COALESCE(NULLIF(c.\"\
  SPECODE2\", ''), '(boş)')\nORDER BY \n    ay,\n    kanal"
source: user
created_at: '2026-09-06T06:41:10.363569+00:00'
---
