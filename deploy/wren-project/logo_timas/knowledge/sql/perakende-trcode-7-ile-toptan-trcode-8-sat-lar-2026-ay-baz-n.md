---
nl: 'Perakende (TRCODE 7) ile toptan (TRCODE 8) satışları 2026 ay bazında karşılaştır:
  her ay için fatura sayısı, NETTOTAL toplamı ve ortalama fatura tutarı; ayrıca perakendenin
  o ayın toplam satışındaki payı.'
sql: "SELECT \n    DATEFROMPARTS(YEAR(\"DATE_\"), MONTH(\"DATE_\"), 1) AS ay,\n  \
  \  SUM(CASE WHEN \"TRCODE\" = 7 THEN 1 ELSE 0 END) AS perakende_fatura_sayisi,\n\
  \    SUM(CASE WHEN \"TRCODE\" = 7 THEN \"NETTOTAL\" ELSE 0 END) AS perakende_toplam,\n\
  \    SUM(CASE WHEN \"TRCODE\" = 7 THEN \"NETTOTAL\" ELSE 0 END) / NULLIF(SUM(CASE\
  \ WHEN \"TRCODE\" = 7 THEN 1 ELSE 0 END), 0) AS perakende_ortalama,\n    SUM(CASE\
  \ WHEN \"TRCODE\" = 8 THEN 1 ELSE 0 END) AS toptan_fatura_sayisi,\n    SUM(CASE\
  \ WHEN \"TRCODE\" = 8 THEN \"NETTOTAL\" ELSE 0 END) AS toptan_toplam,\n    SUM(CASE\
  \ WHEN \"TRCODE\" = 8 THEN \"NETTOTAL\" ELSE 0 END) / NULLIF(SUM(CASE WHEN \"TRCODE\"\
  \ = 8 THEN 1 ELSE 0 END), 0) AS toptan_ortalama,\n    SUM(CASE WHEN \"TRCODE\" =\
  \ 7 THEN \"NETTOTAL\" ELSE 0 END) / NULLIF(SUM(CASE WHEN \"TRCODE\" IN (7,8) THEN\
  \ \"NETTOTAL\" ELSE 0 END), 0) AS perakende_payi\nFROM dbo_LG_411_01_INVOICE\nWHERE\
  \ \"CANCELLED\" = 0\n  AND \"TRCODE\" IN (7, 8)\n  AND \"DATE_\" >= '2026-01-01'\n\
  \  AND \"DATE_\" < '2027-01-01'\nGROUP BY DATEFROMPARTS(YEAR(\"DATE_\"), MONTH(\"\
  DATE_\"), 1)\nORDER BY 1"
source: user
tags:
- verified-2026-09-06
- campaign
---
