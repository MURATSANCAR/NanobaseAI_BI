---
nl: Vadesi geçmiş (vadesi gelmiş ama ödenmemiş) müşteri alacaklarımız toplam ne kadar (FIFO yaklaşımı)
sql: |-
  -- yorum: 'vadesi geçmiş' → FIFO yaklaşımı: Logo'da ödeme kapama yok; cari başına bakiye − vadesi gelmemiş plan satırları
  WITH B AS (SELECT L."CLIENTREF", SUM(CASE WHEN L."SIGN" = 0 THEN L."AMOUNT" ELSE -L."AMOUNT" END) AS bakiye
    FROM LG_CLFLINE L JOIN CLCARD C ON C."LOGICALREF" = L."CLIENTREF"
    WHERE L."CANCELLED" = 0 AND C."CODE" LIKE '120%' AND L."DATE_" >= DATEFROMPARTS(YEAR(GETDATE()), 1, 1)
    GROUP BY L."CLIENTREF"),
  N AS (SELECT P."CARDREF", SUM(P."TOTAL") AS gelmemis FROM PAYTRANS P
    WHERE P."CANCELLED" = 0 AND P."SIGN" = 0 AND P."DATE_" >= CAST(GETDATE() AS date) GROUP BY P."CARDREF")
  SELECT SUM(CASE WHEN B.bakiye - ISNULL(N.gelmemis, 0) > 0 THEN B.bakiye - ISNULL(N.gelmemis, 0) ELSE 0 END) AS vadesi_gecmis_tutar,
    COUNT(CASE WHEN B.bakiye - ISNULL(N.gelmemis, 0) > 0 THEN 1 END) AS cari_sayisi, SUM(B.bakiye) AS toplam_bakiye
  FROM B LEFT JOIN N ON N."CARDREF" = B."CLIENTREF" WHERE B.bakiye > 0
source: user
tags:
- source:enrich
- yontem:fifo
---

Vadesi geçmiş tutar (FIFO): cari hareketleri (LG_CLFLINE; adı yalın CLFLINE olan görünümde tutar kolonları yok) ile ödeme planı (PAYTRANS) CLIENTREF = CARDREF
üzerinden bağlanır; muhasebe fişi (EMFLINE) cariye doğrudan bağlanmaz, kullanılmaz. Carinin bugünkü net
bakiyesinden vadesi henüz gelmemiş plan satırları düşülür, pozitif kalan vadesi geçmiştir. Tedarikçi
(satıcı borcu) aynası: CLCARD.CODE 320%, bakiye SIGN 1 − SIGN 0, PAYTRANS SIGN 1. Sonuç yaklaşıktır.
