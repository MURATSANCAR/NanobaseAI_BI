---
nl: Vadesi gelmiş ama henüz ödenmemiş satıcı (tedarikçi) borçlarımız ne kadar (FIFO yaklaşımı)
sql: |-
  -- yorum: 'vadesi gelmiş ödenmemiş satıcı borcu' → FIFO (320 bakiye ölçüsü tek başına vadeyi ayırmaz) yaklaşımı: Logo'da ödeme kapama yok; cari başına bakiye − vadesi gelmemiş plan satırları
  WITH B AS (SELECT L."CLIENTREF", SUM(CASE WHEN L."SIGN" = 1 THEN L."AMOUNT" ELSE -L."AMOUNT" END) AS bakiye
    FROM LG_CLFLINE L JOIN CLCARD C ON C."LOGICALREF" = L."CLIENTREF"
    WHERE L."CANCELLED" = 0 AND C."CODE" LIKE '320%' AND L."DATE_" >= DATEFROMPARTS(YEAR(GETDATE()), 1, 1)
    GROUP BY L."CLIENTREF"),
  N AS (SELECT P."CARDREF", SUM(P."TOTAL") AS gelmemis FROM PAYTRANS P
    WHERE P."CANCELLED" = 0 AND P."SIGN" = 1 AND P."DATE_" >= CAST(GETDATE() AS date) GROUP BY P."CARDREF")
  SELECT SUM(CASE WHEN B.bakiye - ISNULL(N.gelmemis, 0) > 0 THEN B.bakiye - ISNULL(N.gelmemis, 0) ELSE 0 END) AS vadesi_gecmis_tutar,
    COUNT(CASE WHEN B.bakiye - ISNULL(N.gelmemis, 0) > 0 THEN 1 END) AS cari_sayisi, SUM(B.bakiye) AS toplam_bakiye
  FROM B LEFT JOIN N ON N."CARDREF" = B."CLIENTREF" WHERE B.bakiye > 0
source: user
tags:
- source:enrich
- yontem:fifo
---

Vadesi gelmiş ödenmemiş satıcı borcu (FIFO): 'satıcılar hesabı bakiyesi' (EMFLINE 320) toplam borcu verir,
hangi kısmının vadesinin geldiğini ayırmaz. Tedarikçi carisinin (CLCARD.CODE 320%) LG_CLFLINE bakiyesinden
(SIGN 1 − SIGN 0) vadesi henüz gelmemiş PAYTRANS SIGN 1 plan satırları düşülür; pozitif kalan vadesi
gelmiş borçtur. Kapama yok, sonuç yaklaşıktır.
