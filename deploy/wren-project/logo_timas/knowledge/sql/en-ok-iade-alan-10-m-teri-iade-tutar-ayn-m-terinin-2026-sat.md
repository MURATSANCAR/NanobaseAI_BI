---
nl: 'En çok iade alan 10 müşteri: iade tutarı, aynı müşterinin 2026 satış tutarı,
  iade/satış oranı ve cari kartındaki kanal kodu; yalnız satışı 1 milyon TL üzerinde
  olanlar, iade tutarına göre azalan.'
sql: "SELECT TOP 10\n    c.\"CODE\" AS cari_kodu,\n    c.\"DEFINITION_\" AS unvan,\n\
  \    ISNULL(c.\"SPECODE2\", '(boş)') AS satis_kanali,\n    SUM(CASE WHEN i.\"TRCODE\"\
  \ IN (2,3) THEN i.\"NETTOTAL\" ELSE 0 END) AS iade_tutari,\n    SUM(CASE WHEN i.\"\
  TRCODE\" IN (7,8,9) THEN i.\"NETTOTAL\" ELSE 0 END) AS satis_tutari,\n    CASE \n\
  \        WHEN SUM(CASE WHEN i.\"TRCODE\" IN (7,8,9) THEN i.\"NETTOTAL\" ELSE 0 END)\
  \ = 0 THEN 0\n        ELSE SUM(CASE WHEN i.\"TRCODE\" IN (2,3) THEN i.\"NETTOTAL\"\
  \ ELSE 0 END) / SUM(CASE WHEN i.\"TRCODE\" IN (7,8,9) THEN i.\"NETTOTAL\" ELSE 0\
  \ END)\n    END AS iade_satis_orani\nFROM dbo_LG_411_01_INVOICE i\nJOIN dbo_LG_411_CLCARD\
  \ c ON c.\"LOGICALREF\" = i.\"CLIENTREF\"\nWHERE i.\"CANCELLED\" = 0\n  AND i.\"\
  TRCODE\" IN (2,3,7,8,9)\n  AND i.\"DATE_\" >= '2026-01-01'\n  AND i.\"DATE_\" <\
  \ '2027-01-01'\nGROUP BY c.\"CODE\", c.\"DEFINITION_\", ISNULL(c.\"SPECODE2\", '(boş)')\n\
  HAVING SUM(CASE WHEN i.\"TRCODE\" IN (7,8,9) THEN i.\"NETTOTAL\" ELSE 0 END) > 1000000\n\
  ORDER BY iade_tutari DESC"
source: user
tags:
- verified-2026-09-06
- campaign
---
