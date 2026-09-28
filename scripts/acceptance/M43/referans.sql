-- M43 Depo ve stok — doğrudan SQL referansları (köprü kodu kullanılmaz; Logo .155 / CRM .28 üzerinde salt okunur).
-- kabul.py bunları parametreli koşar; elle denemek için @ değişkenlerini doldurun. Firma: 411 = 2026, 211 = 2021–2025.

-- R1. Logo stok bakiyesi (analiz §14 kabul 1) — katalog tanımı + planlanan üretim girişi hariç (STOCK_EXCLUDE_PLANNED=1).
DECLARE @kod varchar(60) = '15201.01.0001';
SELECT i.CODE, SUM(CASE WHEN l.IOCODE IN (1,2) THEN l.AMOUNT ELSE -l.AMOUNT END) AS bakiye
FROM dbo.LG_411_01_STLINE l JOIN dbo.LG_411_ITEMS i ON i.LOGICALREF = l.STOCKREF
LEFT JOIN dbo.LG_411_01_STFICHE f ON f.LOGICALREF = l.STFICHEREF
WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.IOCODE IN (1,2,3,4) AND NOT (l.TRCODE = 13 AND ISNULL(f.PRODSTAT, 0) = 1)
  AND i.CODE = @kod
GROUP BY i.CODE;
-- Ölçülecek: aynı sorgu PRODSTAT süzgeci olmadan (analizdeki birebir metin); fark = planlanan üretim girişi.

-- R2. Ambar kırılımı toplamı = kitap toplamı (analiz kabul 2): aynı sorgu GROUP BY i.CODE, l.SOURCEINDEX; toplam R1'e eşit.
SELECT i.CODE, l.SOURCEINDEX, SUM(CASE WHEN l.IOCODE IN (1,2) THEN l.AMOUNT ELSE -l.AMOUNT END) AS bakiye
FROM dbo.LG_411_01_STLINE l JOIN dbo.LG_411_ITEMS i ON i.LOGICALREF = l.STOCKREF
LEFT JOIN dbo.LG_411_01_STFICHE f ON f.LOGICALREF = l.STFICHEREF
WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.IOCODE IN (1,2,3,4) AND NOT (l.TRCODE = 13 AND ISNULL(f.PRODSTAT, 0) = 1)
  AND i.CODE = @kod
GROUP BY i.CODE, l.SOURCEINDEX;

-- R3. Satış hızı = Baskı Öneri raporunun «OrtSatisHizi» kolonu (aynı SQL dosyası). kabul.py rapor ucuyla karşılaştırır.

-- R4. Stok devir hızı — katalogdaki sertifikalı ifade (bilinen referans: İYİLİK TİMİ 1,09; aynı kopyada yeniden ölçülür).
SELECT i.CODE, i.NAME,
  SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.AMOUNT END)
    / NULLIF((SUM(CASE WHEN l.TRCODE = 14 THEN l.AMOUNT END)
              + SUM(CASE WHEN l.IOCODE IN (1,2) THEN l.AMOUNT WHEN l.IOCODE IN (3,4) THEN -l.AMOUNT END)) / 2.0, 0) AS devir
FROM dbo.LG_411_01_STLINE l JOIN dbo.LG_411_ITEMS i ON i.LOGICALREF = l.STOCKREF
WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND i.CODE = @kod
GROUP BY i.CODE, i.NAME;

-- R5. Logo'ya aktarılamamış hareket sayısı (analiz kabul 5).
SELECT COUNT(*) AS hata FROM Timas_MSCRM.dbo.new_malzemehareketiBase
WHERE new_logoyaaktarildi = 0 AND statecode = 0 AND new_logomesaji IS NOT NULL;
SELECT COUNT(*) AS bekliyor FROM Timas_MSCRM.dbo.new_malzemehareketiBase
WHERE new_logoyaaktarildi = 0 AND statecode = 0 AND new_logomesaji IS NULL;

-- R6. CRM raf stoğu (analiz kabul 6). «Kalan miktar»ın anlamı ölçülecek (lot bazlı kalan mı, güncel raf stoğu mu).
SELECT p.ProductNumber, SUM(s.new_kalanmiktar) AS raf
FROM Timas_MSCRM.dbo.new_serilothareketsatiriBase s
JOIN Timas_MSCRM.dbo.new_malzemehareketsatiriBase m ON m.new_malzemehareketsatiriId = s.new_malzemehareketsatiriid
JOIN Timas_MSCRM.dbo.ProductBase p ON p.ProductId = m.new_urunid
WHERE s.statecode = 0 AND p.ProductNumber = @kod
GROUP BY p.ProductNumber;

-- R7. Hareketsiz stok (Kural 17, pencere 365 gün, Logo verisinin son gününe kadar; açılış devri TRCODE 14 hareket değil):
--     bakiye > 0 ve pencerede satırı olmayan malzemeler. Pencere iki yıla düşer: 211 ve 411 kopyaları ayrı okunur.
DECLARE @bas date = '2025-08-17', @bit date = '2026-08-18';
WITH bak AS (
  SELECT l.STOCKREF, SUM(CASE WHEN l.IOCODE IN (1,2) THEN l.AMOUNT ELSE -l.AMOUNT END) AS bakiye
  FROM dbo.LG_411_01_STLINE l LEFT JOIN dbo.LG_411_01_STFICHE f ON f.LOGICALREF = l.STFICHEREF
  WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.IOCODE IN (1,2,3,4) AND NOT (l.TRCODE = 13 AND ISNULL(f.PRODSTAT, 0) = 1)
  GROUP BY l.STOCKREF)
SELECT i.CODE, b.bakiye
FROM bak b JOIN dbo.LG_411_ITEMS i ON i.LOGICALREF = b.STOCKREF
WHERE b.bakiye > 0 AND i.CODE NOT LIKE '157%'
  AND NOT EXISTS (SELECT 1 FROM dbo.LG_411_01_STLINE x WHERE x.STOCKREF = b.STOCKREF AND x.LINETYPE = 0 AND x.CANCELLED = 0
                  AND x.TRCODE <> 14 AND x.DATE_ >= @bas AND x.DATE_ < @bit)
  AND NOT EXISTS (SELECT 1 FROM dbo.LG_211_01_STLINE y JOIN dbo.LG_211_ITEMS iy ON iy.LOGICALREF = y.STOCKREF
                  WHERE iy.CODE = i.CODE AND y.LINETYPE = 0 AND y.CANCELLED = 0 AND y.TRCODE <> 14 AND y.DATE_ >= @bas AND y.DATE_ < @bit);

-- R8. Logo bekleyen sipariş (katalog: ORFLINE TRCODE 1, CLOSED 0, CANCELLED 0, LINETYPE 0, AMOUNT − SHIPPEDAMOUNT).
SELECT i.CODE, SUM(o.AMOUNT - o.SHIPPEDAMOUNT) AS bekleyen
FROM dbo.LG_411_01_ORFLINE o JOIN dbo.LG_411_ITEMS i ON i.LOGICALREF = o.STOCKREF
WHERE o.TRCODE = 1 AND o.CLOSED = 0 AND o.CANCELLED = 0 AND o.LINETYPE = 0 AND i.CODE = @kod
GROUP BY i.CODE;

-- R9. CRM bekleyen ürün (durum 1 «Bekleyen», etkin).
SELECT p.ProductNumber, SUM(b.new_adet) AS adet
FROM Timas_MSCRM.dbo.new_bekleyenurunBase b JOIN Timas_MSCRM.dbo.ProductBase p ON p.ProductId = b.new_urunid
WHERE b.statecode = 0 AND b.statuscode = 1 AND p.ProductNumber = @kod
GROUP BY p.ProductNumber;

-- R10. Depo hattı aşama sayıları (CRM sipariş durumu).
SELECT CAST(statuscode AS int) AS durum, COUNT(*) AS adet FROM Timas_MSCRM.dbo.new_siparisBase
WHERE statecode = 0 AND statuscode IN (100000011, 100000012, 100000013, 100000014)
GROUP BY statuscode;
