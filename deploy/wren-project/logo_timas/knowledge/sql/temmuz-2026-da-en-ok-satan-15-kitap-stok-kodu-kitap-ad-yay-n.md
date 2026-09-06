---
nl: 'Temmuz 2026''da en çok satan 15 kitap: stok kodu, kitap adı, yayınevi, satılan
  adet ve brüt satır tutarı; yalnız toptan satış faturaları (TRCODE 8), adede göre
  azalan.'
sql: "SELECT TOP 15\n    it.\"CODE\" AS stok_kodu,\n    it.\"NAME\" AS kitap_adi,\n\
  \    COALESCE(NULLIF(it.\"SPECODE\", ''), '(boş)') AS yayinevi,\n    SUM(sl.\"AMOUNT\"\
  ) AS satilan_adet,\n    SUM(sl.\"TOTAL\") AS brut_satir_tutari\nFROM dbo_LG_411_01_STLINE\
  \ sl\nJOIN dbo_LG_411_ITEMS it ON it.\"LOGICALREF\" = sl.\"STOCKREF\"\nWHERE sl.\"\
  CANCELLED\" = 0\n  AND sl.\"LINETYPE\" = 0\n  AND sl.\"TRCODE\" = 8\n  AND sl.\"\
  DATE_\" >= '2026-07-01'\n  AND sl.\"DATE_\" < '2026-08-01'\nGROUP BY it.\"CODE\"\
  , it.\"NAME\", COALESCE(NULLIF(it.\"SPECODE\", ''), '(boş)')\nORDER BY SUM(sl.\"\
  AMOUNT\") DESC"
source: user
created_at: '2026-09-06T06:41:10.363569+00:00'
---
