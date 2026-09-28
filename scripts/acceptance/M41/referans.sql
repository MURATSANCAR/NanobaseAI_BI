-- M41 Amazon ve yurtdışı — kabulün doğrudan referans sorguları (Logo + CRM, yalnız okuma). kabul.py bunları kendisi koşar.
-- {firma}: verinin son yılının firması (411), {yil}/{ay_sonu}: dönem, {kodlar}: onaylı Amazon cari kodları.

-- K1 · Amazon adlı Logo carileri (ve 211 kopyası, bilgi) + CRM kartlarının Logo bağı.
SELECT CODE, DEFINITION_, SPECODE2 FROM dbo.LG_411_CLCARD WHERE DEFINITION_ LIKE N'%AMAZON%';
SELECT CODE, DEFINITION_, SPECODE2 FROM dbo.LG_211_CLCARD WHERE DEFINITION_ LIKE N'%AMAZON%';
SELECT Name, new_logicalref FROM Timas_MSCRM.dbo.AccountBase WHERE StateCode = 0 AND Name LIKE N'%Amazon%';

-- K2 · Onaylı Amazon carilerinin faturalı net cirosu (M42 kabul 1 tanımı).
SELECT SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET ELSE -l.LINENET END) AS net
FROM dbo.LG_{firma}_01_STLINE l JOIN dbo.LG_{firma}_CLCARD c ON c.LOGICALREF = l.CLIENTREF
WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9)
  AND c.CODE IN ({kodlar}) AND l.DATE_ >= '{yil}-01-01' AND l.DATE_ < '{ay_sonu}';

-- K3 · Konsinye kalan (Kural 18): faturalanmamış satış irsaliyesi − faturalanmamış satış iade irsaliyesi.
SELECT i.CODE, SUM(CASE WHEN l.TRCODE = 8 THEN l.AMOUNT ELSE -l.AMOUNT END) AS kalan,
       SUM(CASE WHEN l.TRCODE = 3 THEN l.AMOUNT ELSE 0 END) AS iade_irsaliyesi
FROM dbo.LG_{firma}_01_STLINE l JOIN dbo.LG_{firma}_ITEMS i ON i.LOGICALREF = l.STOCKREF
JOIN dbo.LG_{firma}_CLCARD c ON c.LOGICALREF = l.CLIENTREF
WHERE l.TRCODE IN (3, 8) AND l.CANCELLED = 0 AND l.LINETYPE = 0 AND l.INVOICEREF = 0 AND l.BILLED = 0
  AND c.CODE IN ({kodlar}) AND l.DATE_ >= '{yil}-01-01' AND l.DATE_ < '{yil_sonrasi}-01-01'
GROUP BY i.CODE;
-- Ölçülecek: yıl devrinde açık irsaliyenin yeni firmaya taşınıp taşınmadığı (AMAZON_KONSINYE_YIL):
SELECT YEAR(l.DATE_) AS yil, COUNT(*) AS satir FROM dbo.LG_211_01_STLINE l JOIN dbo.LG_211_CLCARD c ON c.LOGICALREF = l.CLIENTREF
WHERE l.TRCODE = 8 AND l.INVOICEREF = 0 AND l.BILLED = 0 AND l.CANCELLED = 0 AND c.DEFINITION_ LIKE N'%AMAZON%' GROUP BY YEAR(l.DATE_);

-- K4 · CRM Amazon Konsinye sipariş sayısı (tip 14).
SELECT YEAR(new_siparistarihi) AS yil, COUNT(*) AS n FROM Timas_MSCRM.dbo.new_siparisBase
WHERE statecode = 0 AND new_siparistipi = 14 AND new_siparistarihi >= '{bas}' GROUP BY YEAR(new_siparistarihi);

-- K5 · Yurtdışı net ciro cari bazında (kanal kodu yazımı önce ölçülür).
SELECT DISTINCT SPECODE2 FROM dbo.LG_411_CLCARD WHERE SPECODE2 LIKE N'%YURT%';
SELECT c.CODE, c.COUNTRY, SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET ELSE -l.LINENET END) AS net
FROM dbo.LG_{firma}_01_STLINE l JOIN dbo.LG_{firma}_CLCARD c ON c.LOGICALREF = l.CLIENTREF
WHERE l.LINETYPE = 0 AND l.CANCELLED = 0 AND l.INVOICEREF <> 0 AND l.TRCODE IN (2,3,7,8,9)
  AND c.SPECODE2 IN (N'YURTDIŞI', N'YURTDISI') AND l.DATE_ >= '{yil}-01-01' AND l.DATE_ < '{yil_sonrasi}-01-01'
GROUP BY c.CODE, c.COUNTRY;

-- K6 · Döviz faturası sayısı (katalog notundaki 74 eski ölçüm; aynı kopyada yeniden sayılır).
SELECT COUNT(*) AS toplam, SUM(CASE WHEN TRCODE IN (7,8,9) THEN 1 ELSE 0 END) AS satis
FROM dbo.LG_{firma}_01_INVOICE WHERE CANCELLED = 0 AND ISNULL(TRCURR, 0) NOT IN (0, 160)
  AND DATE_ >= '{yil}-01-01' AND DATE_ < '{yil_sonrasi}-01-01';

-- K7 · Etkin, kitaba bağlı Telif Satış sözleşmesi sayısı.
SELECT COUNT(DISTINCT s.new_sozlesmeId) AS n FROM Timas_MSCRM.dbo.new_sozlesmeBase s
JOIN Timas_MSCRM.dbo.new_new_sozlesme_new_kitapBase sk ON sk.new_sozlesmeid = s.new_sozlesmeId
WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 1;
-- Ölçülecek: «Telif Satılan Ülke» aramasının hedef varlığı (AMAZON_ULKE_TABLOSU, varsayılan new_ulke):
SELECT TOP 5 CAST(new_telifsatilanulke AS nvarchar(200)) AS ulke FROM Timas_MSCRM.dbo.new_sozlesmeBase WHERE new_telifsatilanulke IS NOT NULL;
