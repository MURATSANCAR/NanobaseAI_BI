-- M33 İhale takibi — bağımsız referans sorguları (köprü kodu kullanılmadan; test sunucusunda, salt okunur).
-- Firma numarası yıla göre L_CAPIPERIOD'dan okunur (411 = 2026, 211 = 2021–2025); aşağıda 411 örnektir, kabul.py
-- aynı sorguları firma numarasını yerine koyarak çalıştırır. CRM ve Logo iki ayrı sunucudur: tek sorguda birleşmez,
-- anahtar listesiyle birleştirilir.

-- R1 · Kamu kurumlarına satış (yıl): önce CRM'den kamu kurumlarının Logo cari numaraları …
SELECT new_logicalref FROM Timas_MSCRM.dbo.AccountBase
WHERE StateCode = 0 AND new_KurumRolu IN (2,3) AND new_logicalref IS NOT NULL;
-- … sonra Logo'da o carilere ve satış kanalı KURUM olan carilere faturalı net satış (iade eksi).
SELECT SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.LINENET ELSE -L.LINENET END) AS net_ciro,
       SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.AMOUNT ELSE -L.AMOUNT END) AS net_adet,
       COUNT(DISTINCT L.CLIENTREF) AS cari
FROM dbo.LG_411_01_STLINE L
JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF = L.CLIENTREF
WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9)
  AND L.DATE_ >= '2026-01-01' AND L.DATE_ < '2027-01-01'
  AND (C.SPECODE2 = 'KURUM' OR L.CLIENTREF IN (/* @kamu_clientref listesi */ 0));

-- R2 · ISBN eşleşmesi: şartnamedeki her ISBN için CRM'deki etkin kitap (dört ISBN/barkod alanı).
SELECT new_StokKodu, new_name FROM Timas_MSCRM.dbo.new_kitapBase
WHERE statecode = 0 AND (REPLACE(REPLACE(new_isbn13,'-',''),' ','') = @isbn OR REPLACE(REPLACE(new_ean13,'-',''),' ','') = @isbn
   OR REPLACE(REPLACE(new_isbn,'-',''),' ','') = @isbn10 OR REPLACE(REPLACE(new_EAN10Barkod,'-',''),' ','') = @isbn10);

-- R3 · Stok bakiyesi (tarih filtresiz, güncel firma): giriş − çıkış, planlanan üretim girişi hariç.
SELECT I.CODE, SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT ELSE -L.AMOUNT END) AS stok
FROM dbo.LG_411_01_STLINE L
JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF = L.STOCKREF
LEFT JOIN dbo.LG_411_01_STFICHE F ON F.LOGICALREF = L.STFICHEREF
WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.IOCODE IN (1,2,3,4)
  AND NOT (L.TRCODE = 13 AND ISNULL(F.PRODSTAT, 0) = 1)
  AND I.CODE IN (/* eşleşen stok kodları */ '')
GROUP BY I.CODE;

-- R4 · Liste fiyatı: CRM KDV dahil liste fiyatı ve KDV oranı (TENDER_PRICE_SOURCE=crm; ekranda kaynağı yazılı).
SELECT new_StokKodu, new_kdvdahilfiyat, new_kdvorani FROM Timas_MSCRM.dbo.new_kitapBase
WHERE statecode = 0 AND new_StokKodu IN (/* eşleşen stok kodları */ '');
-- R4b · Logo geçerli satış fiyat listesi (Kural 8): genel liste (cari özel kodu boş) önce, en düşük fiyat.
SELECT I.CODE, P.PRICE, P.CLSPECODE, P.PRIORITY, P.INCVAT FROM dbo.LG_411_PRCLIST P
JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF = P.CARDREF
WHERE P.PTYPE = 2 AND P.ACTIVE = 0 AND P.CURRENCY = 160
  AND P.BEGDATE <= CAST(GETDATE() AS date) AND P.ENDDATE >= CAST(GETDATE() AS date)
  AND I.CODE IN (/* eşleşen stok kodları */ '');

-- R5 · Teklif toplamı = Σ satır(ROUND(adet × birim teklif fiyatı, 2)); KDV ayrı satır (kabul.py ekrandaki kalemlerden hesaplar).

-- R6 · Kamu kurum sayıları (ekrandaki CRM kamu kurumu kutusu).
SELECT new_KurumRolu, COUNT(*) FROM Timas_MSCRM.dbo.AccountBase
WHERE StateCode = 0 AND new_KurumRolu IN (2,3,4) GROUP BY new_KurumRolu;

-- Ö1 · Ölçülecek: ISBN/barkod doluluğu (eşleştirmenin ilk adımı ne kadar kitabı kapsar).
SELECT COUNT(*) AS kitap,
       SUM(CASE WHEN ISNULL(new_isbn13,'') <> '' THEN 1 ELSE 0 END) AS isbn13,
       SUM(CASE WHEN ISNULL(new_ean13,'') <> '' THEN 1 ELSE 0 END) AS barkod,
       SUM(CASE WHEN ISNULL(new_StokKodu,'') <> '' THEN 1 ELSE 0 END) AS stok_kodu,
       SUM(CASE WHEN new_kdvdahilfiyat IS NOT NULL THEN 1 ELSE 0 END) AS fiyat,
       MIN(new_kdvorani) AS kdv_min, MAX(new_kdvorani) AS kdv_max
FROM Timas_MSCRM.dbo.new_kitapBase WHERE statecode = 0;

-- Ö2 · Ölçülecek: new_logicalref biçimi ve güncel firmadaki CLCARD ile örtüşmesi (kabul.py örtüşme oranını yazar).
SELECT TOP 20 new_logicalref, Name FROM Timas_MSCRM.dbo.AccountBase WHERE StateCode = 0 AND new_KurumRolu IN (2,3);

-- Ö3 · Ölçülecek: Logo UNITBARCODE tablosu var mı, kitap barkodu tutuyor mu.
SELECT TOP 20 I.CODE, B.BARCODE FROM dbo.LG_411_UNITBARCODE B JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF = B.ITEMREF WHERE I.ACTIVE = 0;
