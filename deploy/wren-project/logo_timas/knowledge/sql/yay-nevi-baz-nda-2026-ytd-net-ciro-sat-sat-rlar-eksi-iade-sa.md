---
nl: Yayınevi bazında 2026 YTD net ciro (satış satırları eksi iade satırları), satılan
  adet, iade adedi, adet bazlı iade oranı ve maliyetli satırlardan brüt kâr marjı;
  yalnız net cirosu 20 milyon TL üzerindeki yayınevleri, marja göre azalan sırada.
sql: "SELECT \n    COALESCE(NULLIF(it.\"SPECODE\", ''), '(boş)') AS yayinevi,\n  \
  \  SUM(CASE WHEN sl.\"TRCODE\" IN (7,8) THEN sl.\"TOTAL\" ELSE -sl.\"TOTAL\" END)\
  \ AS net_ciro,\n    SUM(CASE WHEN sl.\"TRCODE\" IN (7,8) THEN sl.\"AMOUNT\" ELSE\
  \ 0 END) AS satilan_adet,\n    SUM(CASE WHEN sl.\"TRCODE\" IN (2,3) THEN sl.\"AMOUNT\"\
  \ ELSE 0 END) AS iade_adedi,\n    SUM(CASE WHEN sl.\"TRCODE\" IN (2,3) THEN sl.\"\
  AMOUNT\" ELSE 0 END) / NULLIF(SUM(CASE WHEN sl.\"TRCODE\" IN (7,8) THEN sl.\"AMOUNT\"\
  \ ELSE 0 END), 0) AS adet_iade_orani,\n    1 - SUM(CASE WHEN sl.\"TRCODE\" IN (7,8)\
  \ AND sl.\"OUTCOST\" <> 0 THEN sl.\"AMOUNT\" * sl.\"OUTCOST\" ELSE 0 END) / NULLIF(SUM(CASE\
  \ WHEN sl.\"TRCODE\" IN (7,8) AND sl.\"OUTCOST\" <> 0 THEN sl.\"TOTAL\" ELSE 0 END),\
  \ 0) AS brut_kar_marji\nFROM dbo_LG_411_01_STLINE sl\nJOIN dbo_LG_411_ITEMS it ON\
  \ it.\"LOGICALREF\" = sl.\"STOCKREF\"\nWHERE sl.\"CANCELLED\" = 0 \n  AND sl.\"\
  LINETYPE\" = 0 \n  AND sl.\"TRCODE\" IN (2,3,7,8)\n  AND sl.\"DATE_\" >= '2026-01-01'\
  \ \n  AND sl.\"DATE_\" < '2027-01-01'\nGROUP BY COALESCE(NULLIF(it.\"SPECODE\",\
  \ ''), '(boş)')\nHAVING SUM(CASE WHEN sl.\"TRCODE\" IN (7,8) THEN sl.\"TOTAL\" ELSE\
  \ -sl.\"TOTAL\" END) > 20000000\nORDER BY brut_kar_marji DESC"
source: user
tags:
- verified-2026-09-06
- campaign
---
