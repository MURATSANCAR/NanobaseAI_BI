---
nl: 'Müşteri yoğunlaşması: 2026 net ciroya (satış eksi iade) göre ilk 10 müşterinin
  toplam net ciro içindeki payı yüzde olarak; her müşteri için net ciro, kümülatif
  pay ve kanal kodu.'
sql: "WITH customer_net AS (\n    SELECT \n        c.\"CODE\" AS cari_kodu,\n    \
  \    c.\"DEFINITION_\" AS unvan,\n        COALESCE(NULLIF(c.\"SPECODE2\", ''), '(boş)')\
  \ AS kanal_kodu,\n        SUM(CASE WHEN i.\"TRCODE\" IN (7,8,9) THEN i.\"NETTOTAL\"\
  \ ELSE -i.\"NETTOTAL\" END) AS net_ciro\n    FROM dbo_LG_411_01_INVOICE i\n    JOIN\
  \ dbo_LG_411_CLCARD c ON c.\"LOGICALREF\" = i.\"CLIENTREF\"\n    WHERE i.\"CANCELLED\"\
  \ = 0\n      AND i.\"TRCODE\" IN (2,3,7,8,9)\n      AND i.\"DATE_\" >= '2026-01-01'\n\
  \      AND i.\"DATE_\" < '2027-01-01'\n    GROUP BY c.\"CODE\", c.\"DEFINITION_\"\
  , COALESCE(NULLIF(c.\"SPECODE2\", ''), '(boş)')\n),\nranked AS (\n    SELECT \n\
  \        cari_kodu,\n        unvan,\n        kanal_kodu,\n        net_ciro,\n  \
  \      SUM(net_ciro) OVER (ORDER BY net_ciro DESC ROWS BETWEEN UNBOUNDED PRECEDING\
  \ AND CURRENT ROW) AS kumulatif_ciro,\n        SUM(net_ciro) OVER () AS toplam_net_ciro\n\
  \    FROM customer_net\n)\nSELECT TOP 10\n    cari_kodu,\n    unvan,\n    kanal_kodu,\n\
  \    net_ciro,\n    (net_ciro / NULLIF(toplam_net_ciro, 0)) * 100 AS pay_yuzde,\n\
  \    (kumulatif_ciro / NULLIF(toplam_net_ciro, 0)) * 100 AS kumulatif_pay_yuzde\n\
  FROM ranked\nORDER BY net_ciro DESC"
source: user
tags:
- verified-2026-09-06
- campaign
---
