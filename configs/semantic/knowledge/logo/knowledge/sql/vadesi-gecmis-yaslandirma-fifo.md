---
nl: Müşteri alacaklarını vadesine göre 30, 60, 90 gün yaşlandır (FIFO yaklaşımı)
sql: |-
  -- yorum: 'yaşlandırma' → FIFO yaklaşımı: Logo'da ödeme kapama yok; cari bakiyesi en yeni vade satırlarından geriye dağıtılır
  WITH B AS (SELECT L."CLIENTREF", SUM(CASE WHEN L."SIGN" = 0 THEN L."AMOUNT" ELSE -L."AMOUNT" END) AS bakiye
    FROM CLFLINE L JOIN CLCARD C ON C."LOGICALREF" = L."CLIENTREF"
    WHERE L."CANCELLED" = 0 AND C."CODE" LIKE '120%' AND L."DATE_" >= DATEFROMPARTS(YEAR(GETDATE()), 1, 1)
    GROUP BY L."CLIENTREF"),
  P AS (SELECT P."CARDREF", P."DATE_", P."TOTAL",
      SUM(P."TOTAL") OVER (PARTITION BY P."CARDREF" ORDER BY P."DATE_" DESC, P."LOGICALREF" DESC ROWS UNBOUNDED PRECEDING) AS kumulatif
    FROM PAYTRANS P WHERE P."CANCELLED" = 0 AND P."SIGN" = 0 AND P."CARDREF" IN (SELECT "CLIENTREF" FROM B WHERE bakiye > 0)),
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

Yaşlandırma / vadesi geçmiş (FIFO): Logo'da ödeme kapama kullanılmıyor (116.514 plan satırının 14'ünde
ödenen tutar dolu). Carinin bugünkü net bakiyesi, o carinin en yeni vade (PAYTRANS) satırlarından geriye
doğru dağıtılır; daha eski satırlar ödenmiş sayılır. Vadesi geçmiş toplam = kovalardaki 1-30 … 90+ toplamı
(ya da cari başına max(0, bakiye − vadesi gelmemiş plan satırları)). Tedarikçi aynası: 320%, CLFLINE
bakiyesi alacak − borç, PAYTRANS SIGN 1. Sonuç yaklaşıktır ve cevapta öyle söylenir.
