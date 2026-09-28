-- M40 Trendyol — kabulün doğrudan referans sorguları (Logo, yalnız okuma). kabul.py bunları kendisi koşar; elle denemek
-- için {firma} güncel yıl firması (411), {yil}/{ay_sonu} verinin son yılı ve ayı, {kodlar} onaylı Trendyol cari kodları.

-- K1 · Unvanında platform adı geçen cariler (Yönetim ayarı TRENDYOL_CARI_ADLARI; varsayılan TRENDYOL, DSM GRUP).
--      Boş sonuç «Trendyol'a satış yok» diye sunulmaz; 211 kopyasında da bakılır (bilgi).
SELECT CODE, DEFINITION_, SPECODE2 FROM dbo.LG_411_CLCARD WHERE DEFINITION_ LIKE N'%TRENDYOL%' OR DEFINITION_ LIKE N'%DSM GRUP%';
SELECT CODE, DEFINITION_, SPECODE2 FROM dbo.LG_211_CLCARD WHERE DEFINITION_ LIKE N'%TRENDYOL%' OR DEFINITION_ LIKE N'%DSM GRUP%';

-- K2 · Toptan senaryo: onaylı Trendyol carilerinin faturalı net cirosu (M42 tanımı; LINENET satış − iade).
SELECT SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET ELSE -l.LINENET END) AS net
FROM dbo.LG_{firma}_01_STLINE l JOIN dbo.LG_{firma}_CLCARD c ON c.LOGICALREF = l.CLIENTREF
WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9)
  AND c.CODE IN ({kodlar}) AND l.DATE_ >= '{yil}-01-01' AND l.DATE_ < '{ay_sonu}';

-- K4 · Depo stok bakiyesi (M34/M43 tanımı): giriş − çıkış, planlanan üretim girişi hariç.
SELECT I.CODE AS stok, SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
FROM dbo.LG_{firma}_01_STLINE L JOIN dbo.LG_{firma}_ITEMS I ON I.LOGICALREF = L.STOCKREF
LEFT JOIN dbo.LG_{firma}_01_STFICHE F ON F.LOGICALREF = L.STFICHEREF
WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.IOCODE IN (1,2,3,4) AND NOT (L.TRCODE = 13 AND ISNULL(F.PRODSTAT, 0) = 1)
  AND I.CODE IN ({stok_kodlari})
GROUP BY I.CODE;

-- K6 · Bugün geçerli liste fiyatı: satış listesi, TL, cariye bağlı olmayan önce, küçük öncelik, en yeni başlangıç.
SELECT TOP 1 P.PRICE, P.INCVAT FROM dbo.LG_{firma}_PRCLIST P JOIN dbo.LG_{firma}_ITEMS I ON I.LOGICALREF = P.CARDREF
WHERE I.CODE = N'{stok_kodu}' AND P.PTYPE = 2 AND P.ACTIVE = 0 AND P.CURRENCY = 160 AND P.PRICE > 0
  AND P.BEGDATE <= CAST(GETDATE() AS date) AND (P.ENDDATE >= CAST(GETDATE() AS date) OR P.ENDDATE IS NULL)
ORDER BY CASE WHEN ISNULL(P.CLIENTCODE, '') = '' AND ISNULL(P.CLSPECODE, '') = '' THEN 0 ELSE 1 END, P.PRIORITY, P.BEGDATE DESC;

-- K7 · Barkod → stok kodu eşlemesinin kaynağı: farklı dolu barkod sayısı.
SELECT COUNT(DISTINCT REPLACE(LTRIM(RTRIM(B.BARCODE)), ' ', '')) AS n FROM dbo.LG_{firma}_UNITBARCODE B
JOIN dbo.LG_{firma}_ITEMS I ON I.LOGICALREF = B.ITEMREF WHERE B.BARCODE IS NOT NULL AND LTRIM(RTRIM(B.BARCODE)) <> '';

-- Ölçülecek (kabulde bilgi): Trendyol barkodunun EAN-13 olup olmadığı — yüklenen ürün listesinde «Barkod Logo'da
-- bulunamadı» sayısı; kitap KDV oranı (TRENDYOL_LISTE_KDV) — PRCLIST.INCVAT doluluğu:
SELECT P.INCVAT, COUNT(*) AS n FROM dbo.LG_411_PRCLIST P WHERE P.PTYPE = 2 AND P.ACTIVE = 0 GROUP BY P.INCVAT;
