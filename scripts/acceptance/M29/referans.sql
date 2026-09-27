-- M29 İlk dağılım — doğrudan SQL referansları (köprü kopyası değil; Logo .155 / CRM .28 üzerinde salt okunur).
-- kabul.py bunları parametreli koşar; elle denemek için @ değişkenleri doldurun. Firma: 411 = 2026, 211 = 2021–2025.

-- R1. Depoya giriş (dağılım bekleyen listesi): kitap başına pencere içindeki ilk gün ve adet. Yalnız gerçek giriş
--     fişi (PRODSTAT 0); planlanan fiş (1) M12 ölçümüne göre adedi ikiye katlar. Analizdeki sorgudan farkı bu süzgeç.
DECLARE @bas date = '2026-06-30';
SELECT I.CODE, MIN(L.DATE_) AS giris, SUM(L.AMOUNT) AS adet
FROM LG_411_01_STLINE L JOIN LG_411_01_STFICHE F ON F.LOGICALREF = L.STFICHEREF
JOIN LG_411_ITEMS I ON I.LOGICALREF = L.STOCKREF
WHERE L.TRCODE = 13 AND L.IOCODE = 1 AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND F.CANCELLED = 0 AND F.PRODSTAT = 0
  AND L.DATE_ >= @bas AND I.CODE LIKE '15201%'
GROUP BY I.CODE;
-- Ölçülecek: PRODSTAT süzgeci olmadan aynı sorgu (fark = planlanan fiş adedi).

-- R2. Stok bakiyesi (tarih süzgeci yok, güncel kopya; planlanan üretim girişi hariç).
DECLARE @kod varchar(60) = '15201.01.0001';
SELECT I.CODE, SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
FROM LG_411_01_STLINE L JOIN LG_411_ITEMS I ON I.LOGICALREF = L.STOCKREF
LEFT JOIN LG_411_01_STFICHE F ON F.LOGICALREF = L.STFICHEREF
WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.IOCODE IN (1,2,3,4) AND NOT (L.TRCODE = 13 AND ISNULL(F.PRODSTAT, 0) = 1)
  AND I.CODE = @kod
GROUP BY I.CODE;
-- Ölçülecek: katalogdaki «stok bakiyesi» (planlanan fiş dahil) ile fark; DIST_STOCK_EXCLUDE_PLANNED kararının dayanağı.

-- R3. Benzer kitabın ilk 56 gün kanal dağılımı (net adet = satış − iade; faturalı satır). Pencere başı = ilk faturalı satış.
DECLARE @comp varchar(60) = '15201.01.0002', @ilk date = '2025-03-01';
SELECT C.SPECODE2 AS kanal,
  SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.AMOUNT ELSE 0 END) - SUM(CASE WHEN L.TRCODE IN (2,3) THEN L.AMOUNT ELSE 0 END) AS net_adet
FROM LG_211_01_STLINE L JOIN LG_211_CLCARD C ON C.LOGICALREF = L.CLIENTREF
JOIN LG_211_ITEMS I ON I.LOGICALREF = L.STOCKREF
WHERE I.CODE = @comp AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9)
  AND L.DATE_ >= @ilk AND L.DATE_ < DATEADD(day, 56, @ilk)
GROUP BY C.SPECODE2;

-- R4. Geçmiş ilk dağılım (CRM «Dağılım» tipli, etkin, iptal edilmemiş sipariş satırları).
SELECT SUM(ss.new_siparisadedi) AS adet, COUNT(DISTINCT s.new_siparisId) AS siparis
FROM Timas_MSCRM.dbo.new_siparisBase s JOIN Timas_MSCRM.dbo.new_siparissatiriBase ss ON ss.new_siparisid = s.new_siparisId
WHERE s.new_siparistipi = 2 AND s.statecode = 0 AND ss.statecode = 0 AND ISNULL(s.statuscode, 0) <> 100000001
  AND ss.new_StokKodu = @comp;

-- R5. Takip: kitap × cari sevk (irsaliye TRCODE 7/8, IOCODE 4), faturalanan ve iade, onay gününden 8 hafta.
DECLARE @onay date = '2026-06-01';
SELECT C.CODE,
  SUM(CASE WHEN L.TRCODE IN (7,8) AND L.IOCODE = 4 THEN L.AMOUNT ELSE 0 END) AS sevk,
  SUM(CASE WHEN L.TRCODE IN (7,8,9) AND L.INVOICEREF <> 0 THEN L.AMOUNT ELSE 0 END) AS fatura,
  SUM(CASE WHEN L.TRCODE IN (2,3) THEN L.AMOUNT ELSE 0 END) AS iade
FROM LG_411_01_STLINE L JOIN LG_411_CLCARD C ON C.LOGICALREF = L.CLIENTREF JOIN LG_411_ITEMS I ON I.LOGICALREF = L.STOCKREF
WHERE I.CODE = @kod AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.TRCODE IN (2,3,7,8,9)
  AND L.DATE_ >= @onay AND L.DATE_ < DATEADD(day, 56, @onay)
GROUP BY C.CODE;

-- R6. Dağılım carileri (CRM «Dağılım Durumu Göster»). Planda cari koduyla tekilleştirilir; kodu olmayan ayrı satır.
SELECT COUNT(*) AS kayit,
  COUNT(DISTINCT COALESCE(NULLIF(new_CariKodu, ''), CAST(AccountId AS nvarchar(40)))) AS tekil
FROM Timas_MSCRM.dbo.AccountBase WHERE new_distributionstatus = 1 AND StateCode = 0;

-- R7. (Ölçülecek, rezerv kararı) Son 2 yılın ilk baskılarında depo girişinden sonraki 56 günde sevk edilen / basılan.
--     DIST_RESERVE_SHARE varsayılanı (%20) bu oranın 1 − ortancası ile karşılaştırılır.
SELECT I.CODE, MIN(G.giris) AS giris, MAX(G.adet) AS basilan,
  SUM(CASE WHEN L.TRCODE IN (7,8) AND L.IOCODE = 4 AND L.DATE_ < DATEADD(day, 56, G.giris) THEN L.AMOUNT ELSE 0 END) AS sevk_56
FROM (SELECT L2.STOCKREF, MIN(L2.DATE_) AS giris, SUM(L2.AMOUNT) AS adet FROM LG_411_01_STLINE L2
      JOIN LG_411_01_STFICHE F2 ON F2.LOGICALREF = L2.STFICHEREF
      WHERE L2.TRCODE = 13 AND L2.IOCODE = 1 AND L2.LINETYPE = 0 AND L2.CANCELLED = 0 AND F2.PRODSTAT = 0 GROUP BY L2.STOCKREF) G
JOIN LG_411_ITEMS I ON I.LOGICALREF = G.STOCKREF
JOIN LG_411_01_STLINE L ON L.STOCKREF = G.STOCKREF AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.DATE_ >= G.giris
WHERE I.CODE LIKE '15201%'
GROUP BY I.CODE;
