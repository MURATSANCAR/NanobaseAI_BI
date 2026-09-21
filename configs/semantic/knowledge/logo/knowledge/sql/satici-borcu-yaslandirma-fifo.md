---
nl: Satıcı (tedarikçi) borçlarımızı vadesine göre yaşlandırır mısın (FIFO yaklaşımı)
sql: |-
  -- yorum: 'yaşlandırma' (satıcı borcu) → FIFO yaklaşımı: Logo'da ödeme kapama yok; cari bakiyesi en yeni vade satırlarından geriye dağıtılır
  WITH B AS (SELECT L."CLIENTREF", SUM(CASE WHEN L."SIGN" = 1 THEN L."AMOUNT" ELSE -L."AMOUNT" END) AS bakiye
    FROM LG_CLFLINE L JOIN CLCARD C ON C."LOGICALREF" = L."CLIENTREF"
    WHERE L."CANCELLED" = 0 AND C."CODE" LIKE '320%' AND L."DATE_" >= DATEFROMPARTS(YEAR(GETDATE()), 1, 1)
    GROUP BY L."CLIENTREF"),
  P AS (SELECT P."CARDREF", P."DATE_", P."TOTAL",
      SUM(P."TOTAL") OVER (PARTITION BY P."CARDREF" ORDER BY P."DATE_" DESC, P."LOGICALREF" DESC ROWS UNBOUNDED PRECEDING) AS kumulatif
    FROM PAYTRANS P WHERE P."CANCELLED" = 0 AND P."SIGN" = 1 AND P."CARDREF" IN (SELECT "CLIENTREF" FROM B WHERE bakiye > 0)),
  A AS (SELECT P."CARDREF", P."DATE_",
      CASE WHEN B.bakiye >= P.kumulatif THEN P."TOTAL" WHEN B.bakiye > P.kumulatif - P."TOTAL" THEN B.bakiye - (P.kumulatif - P."TOTAL") ELSE 0 END AS acik
    FROM P JOIN B ON B."CLIENTREF" = P."CARDREF")
  SELECT kova, SUM(acik) AS tutar, COUNT(DISTINCT "CARDREF") AS cari_sayisi FROM (
    SELECT A."CARDREF", A.acik, CASE WHEN DATEDIFF(day, A."DATE_", CAST(GETDATE() AS date)) <= 0 THEN '0 vadesi gelmemiş'
      WHEN DATEDIFF(day, A."DATE_", CAST(GETDATE() AS date)) <= 30 THEN '1 1-30 gün'
      WHEN DATEDIFF(day, A."DATE_", CAST(GETDATE() AS date)) <= 60 THEN '2 31-60 gün'
      WHEN DATEDIFF(day, A."DATE_", CAST(GETDATE() AS date)) <= 90 THEN '3 61-90 gün' ELSE '4 90+ gün' END AS kova
    FROM A WHERE A.acik > 0) x GROUP BY kova ORDER BY kova
source: user
tags:
- source:enrich
- yontem:fifo
---

Satıcı borcu yaşlandırması (FIFO, müşteri yaşlandırmasının aynası): tedarikçi carileri (CLCARD.CODE 320%),
bakiye alacak − borç (SIGN 1 − SIGN 0), vade satırları PAYTRANS SIGN 1. 'Vadesine göre' ödeme planı
satırının vade tarihidir (PAYTRANS.DATE_), stok/fiyat vade kodu değil. Kapama yok, sonuç yaklaşıktır.
