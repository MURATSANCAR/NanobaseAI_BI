---
nl: 'Kanal bazında brüt kâr marjı: satış hareket satırlarında (TRCODE 7,8, LINETYPE
  0, maliyeti işlenmiş satırlar) faturanın cari kartındaki kanal koduna göre maliyetli
  ciro, maliyet ve marj yüzdesi; maliyetli cirosu 10 milyon TL üzerindeki kanallar,
  marja göre azalan.'
sql: "SELECT \n    COALESCE(NULLIF(c.\"SPECODE2\", ''), '(boş)') AS kanal,\n    SUM(s.\"\
  TOTAL\") AS maliyetli_ciro,\n    SUM(s.\"AMOUNT\" * s.\"OUTCOST\") AS toplam_maliyet,\n\
  \    (1 - SUM(s.\"AMOUNT\" * s.\"OUTCOST\") / NULLIF(SUM(s.\"TOTAL\"), 0)) * 100\
  \ AS brut_kar_marji_yuzde\nFROM dbo_LG_411_01_STLINE s\nJOIN dbo_LG_411_01_INVOICE\
  \ i ON i.\"LOGICALREF\" = s.\"INVOICEREF\"\nJOIN dbo_LG_411_CLCARD c ON c.\"LOGICALREF\"\
  \ = i.\"CLIENTREF\"\nWHERE s.\"CANCELLED\" = 0\n  AND s.\"LINETYPE\" = 0\n  AND\
  \ s.\"OUTCOST\" <> 0\n  AND i.\"CANCELLED\" = 0\n  AND i.\"TRCODE\" IN (7, 8)\n\
  GROUP BY COALESCE(NULLIF(c.\"SPECODE2\", ''), '(boş)')\nHAVING SUM(s.\"TOTAL\")\
  \ > 10000000\nORDER BY brut_kar_marji_yuzde DESC"
source: user
tags:
- verified-2026-09-06
- campaign
---
