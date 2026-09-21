---
nl: Ortalama tahsilat süremiz kaç gün (DSO yaklaşımı)
sql: |-
  -- yorum: 'tahsilat süresi' → DSO yaklaşımı: Logo'da ödeme kapama kullanılmadığı için gerçekleşen süre ölçülemez; müşteri bakiyesi ÷ satış × gün
  WITH B AS (SELECT SUM(CASE WHEN L."SIGN" = 0 THEN L."AMOUNT" ELSE -L."AMOUNT" END) AS bakiye
    FROM CLFLINE L JOIN CLCARD C ON C."LOGICALREF" = L."CLIENTREF"
    WHERE L."CANCELLED" = 0 AND C."CODE" LIKE '120%' AND L."DATE_" >= DATEFROMPARTS(YEAR(GETDATE()), 1, 1)),
  S AS (SELECT SUM(CASE WHEN L."TRCODE" IN (37, 38, 39) THEN L."AMOUNT" WHEN L."TRCODE" IN (32, 33) THEN -L."AMOUNT" ELSE 0 END) AS satis,
    DATEDIFF(day, DATEFROMPARTS(YEAR(GETDATE()), 1, 1), MAX(L."DATE_")) + 1 AS gun
    FROM CLFLINE L JOIN CLCARD C ON C."LOGICALREF" = L."CLIENTREF"
    WHERE L."CANCELLED" = 0 AND C."CODE" LIKE '120%' AND L."DATE_" >= DATEFROMPARTS(YEAR(GETDATE()), 1, 1))
  SELECT B.bakiye AS musteri_bakiyesi, S.satis AS satis_faturalari, S.gun,
    ROUND(B.bakiye / NULLIF(S.satis, 0) * S.gun, 1) AS ortalama_tahsilat_suresi_gun FROM B CROSS JOIN S
source: user
tags:
- source:enrich
- yontem:dso
---

Ortalama tahsilat süresi (DSO): Logo'da ödeme kapama (PAYTRANS PAID/CROSSREF) kullanılmadığından hangi
faturanın ne zaman tahsil edildiği bilinmez. Standart muhasebe yaklaşımı: müşteri carilerinin (120%)
bugünkü net bakiyesi ÷ yıl başından bu yana müşteri satış faturaları × geçen gün. Ödeme süresi (DPO)
aynası tedarikçi (320%) carileri, SIGN ters, TRCODE 31, 34 (− 36) ile hesaplanır. Sonuç yaklaşıktır.
