---
nl: 2026'da mal alım (TRCODE 1) ve alınan hizmet (TRCODE 4) faturalarında tedarikçi
  (cari) bazında toplam tutar, fatura sayısı, ilk ve son fatura tarihi; toplam tutara
  göre ilk 10 tedarikçi, cari unvanıyla.
sql: "SELECT TOP 10\n    \"CLCARD\".\"DEFINITION_\" AS \"CARI_UNVANI\",\n    SUM(\"\
  INVOICE\".\"NETTOTAL\") AS \"TOPLAM_TUTAR\",\n    COUNT(\"INVOICE\".\"LOGICALREF\"\
  ) AS \"FATURA_SAYISI\",\n    MIN(\"INVOICE\".\"DATE_\") AS \"ILK_FATURA_TARIHI\"\
  ,\n    MAX(\"INVOICE\".\"DATE_\") AS \"SON_FATURA_TARIHI\"\nFROM \"dbo_LG_411_01_INVOICE\"\
  \ AS \"INVOICE\"\nINNER JOIN \"dbo_LG_411_CLCARD\" AS \"CLCARD\"\n    ON \"INVOICE\"\
  .\"CLIENTREF\" = \"CLCARD\".\"LOGICALREF\"\nWHERE \"INVOICE\".\"CANCELLED\" = 0\n\
  \    AND \"INVOICE\".\"TRCODE\" IN (1, 4)\n    AND \"INVOICE\".\"DATE_\" >= '2026-01-01'\n\
  \    AND \"INVOICE\".\"DATE_\" < '2027-01-01'\nGROUP BY \"CLCARD\".\"DEFINITION_\"\
  \nORDER BY SUM(\"INVOICE\".\"NETTOTAL\") DESC"
source: user
tags:
- verified-2026-09-06
- campaign
---
