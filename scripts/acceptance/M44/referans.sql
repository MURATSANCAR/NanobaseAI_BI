-- M44 Lojistik ve kargo — bağımsız referans sorguları (köprü kodu kullanılmadan; test sunucusunda, salt okunur).
-- CRM (192.168.0.28, Timas_MSCRM) ve Logo iki ayrı sunucudur: tek sorguda birleşmez. Logo firma numarası yıla göre
-- L_CAPIPERIOD'dan okunur (411 = 2026); aşağıda 411 örnektir, kabul.py yerine koyar. @bas/@bit gibi değerleri kabul.py
-- API'nin kullandığı dönemden alır. CRM tarihleri UTC saklanır: İstanbul gününün başı = önceki gün 21:00 UTC.
-- Kargo firması (new_kargofirmasiBase) kimlik kolonları (kullanıcı adı, şifre, token, client id/secret) hiçbir sorguda yok.

-- R1 · Son N gün sevk edilen sipariş (kabul 1; durumlar SHIPPING_SHIPPED_STATUSES).
SELECT COUNT(*) AS adet
FROM Timas_MSCRM.dbo.new_siparisBase
WHERE statecode = 0 AND statuscode IN (100000000, 100000015) AND new_sevktarihi >= @bas_utc;

-- R2 · Firma bazında desi başı maliyet (kabul 2; Kural C19: metin, ondalık virgül). Dönem kargo irsaliye tarihine göre.
SELECT UPPER(LTRIM(RTRIM(new_kargofirmasi))) AS firma, COUNT(*) AS gonderi,
       SUM(TRY_CAST(REPLACE(new_Tutar, ',', '.') AS FLOAT)) AS tutar,
       SUM(TRY_CAST(REPLACE(new_desi, ',', '.') AS FLOAT)) AS desi,
       SUM(TRY_CAST(REPLACE(new_Tutar, ',', '.') AS FLOAT)) / NULLIF(SUM(TRY_CAST(REPLACE(new_desi, ',', '.') AS FLOAT)), 0) AS desi_basi
FROM Timas_MSCRM.dbo.new_kargobilgisiBase
WHERE statecode = 0
  AND CAST(COALESCE(TRY_CONVERT(datetime, new_kargoirstarihi, 104), TRY_CONVERT(datetime, new_kargoirstarihi, 103),
                    TRY_CONVERT(datetime, new_kargoirstarihi, 120), TRY_CONVERT(datetime, new_kargoirstarihi, 112)) AS date) >= @bas
  AND CAST(COALESCE(TRY_CONVERT(datetime, new_kargoirstarihi, 104), TRY_CONVERT(datetime, new_kargoirstarihi, 103),
                    TRY_CONVERT(datetime, new_kargoirstarihi, 120), TRY_CONVERT(datetime, new_kargoirstarihi, 112)) AS date) < @bit
GROUP BY UPPER(LTRIM(RTRIM(new_kargofirmasi)));

-- R3 · Çıkış şubesine göre sevk adedi başına maliyet (Kural C19; boş şube «Belirtilmemiş»), aynı dönem.
SELECT ISNULL(NULLIF(LTRIM(RTRIM(new_sevkiyatcikissubesi)), ''), 'Belirtilmemiş') AS sube, COUNT(*) AS gonderi,
       SUM(TRY_CAST(REPLACE(new_Tutar, ',', '.') AS FLOAT)) / NULLIF(SUM(TRY_CAST(REPLACE(new_sevkadeti, ',', '.') AS FLOAT)), 0) AS sevk_basi
FROM Timas_MSCRM.dbo.new_kargobilgisiBase
WHERE statecode = 0 AND /* R2'deki dönem koşulu */ 1 = 1
GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(new_sevkiyatcikissubesi)), ''), 'Belirtilmemiş');

-- R4 · Entegrasyon hatası adayları (kabul 4): takip no yok, dört firmadan birinde sonuç/mesaj dolu, pencere sipariş tarihinden.
-- «Başarılı» değerleri kabul.py'de SHIPPING_INTEGRATION_OK_VALUES ile elenir (değer kümesi --olcum ile ölçülür).
SELECT new_siparisId, new_araskargoentegrasyonsonucu, CAST(new_araskargoentegrasyonmesaji AS nvarchar(max)) AS aras_mesaj,
       new_upskargoentegrasyonsonucu, CAST(new_upskargoentegrasyonmesaji AS nvarchar(max)) AS ups_mesaj,
       new_mngkargoentegrasyonsonucu, new_mngkargoentegrasyonmesaji,
       new_akademikargoentegrasyonsonucu, CAST(new_akademikargoentegrasyonmesaji AS nvarchar(max)) AS akademi_mesaj
FROM Timas_MSCRM.dbo.new_siparisBase
WHERE statecode = 0 AND ISNULL(new_kargotakipno, '') = '' AND statuscode NOT IN (100000001, 100000003, 2, 1)
  AND new_siparistarihi >= @bas;

-- R5 · Takip numarasız sevk (kabul 5; durumlar SHIPPING_UNTRACKED_STATUSES), pencere sevk tarihinden.
SELECT COUNT(*) AS adet
FROM Timas_MSCRM.dbo.new_siparisBase
WHERE statecode = 0 AND statuscode = 100000000 AND ISNULL(new_kargotakipno, '') = '' AND new_sevktarihi >= @bas;

-- R6 · Logo sevk (Kural 10) ile CRM sevkiyatı, bir ay (kabul 6). Logo: irsaliye fişi ve faturalanmış olanların fatura no'su …
SELECT S.STFICHEREF, MAX(I.FICHENO) AS fatura_no, COUNT(*) AS satir
FROM dbo.LG_411_01_STLINE S
LEFT JOIN dbo.LG_411_01_INVOICE I ON I.LOGICALREF = S.INVOICEREF AND S.INVOICEREF <> 0
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.TRCODE IN (7,8) AND S.IOCODE = 4 AND S.DATE_ >= @ay_bas AND S.DATE_ < @ay_bit
GROUP BY S.STFICHEREF;
-- … CRM: Logo'ya aktarıldı işaretli sevkiyatlar (fatura no ile eşlenir).
SELECT new_faturanumarasi FROM Timas_MSCRM.dbo.new_sevkiyatBase
WHERE statecode = 0 AND new_logoyaaktarildi = 1 AND new_sevktarihi >= @ay_bas_utc AND new_sevktarihi < @ay_bit_utc;

-- R7 · Teslim bekleyen (teslim tarihi okunamayan/boş, iade değil).
SELECT COUNT(*) AS adet
FROM Timas_MSCRM.dbo.new_kargobilgisiBase
WHERE statecode = 0
  AND COALESCE(TRY_CONVERT(datetime, new_TeslimTarihi, 104), TRY_CONVERT(datetime, new_TeslimTarihi, 103),
               TRY_CONVERT(datetime, new_TeslimTarihi, 120), TRY_CONVERT(datetime, new_TeslimTarihi, 112)) IS NULL
  AND (ISNULL(LTRIM(RTRIM(new_iadedurumu)), '') = '' OR LOWER(LTRIM(RTRIM(new_iadedurumu))) IN (N'hayır', 'hayir', 'yok', '0', 'false', '-', 'normal', N'iade değil'));

-- R8 · Gönderi kartı: rastgele bir sevk edilmiş siparişin sevkiyat ve takip kaydı sayısı.
SELECT TOP 1 new_siparisId, new_name FROM Timas_MSCRM.dbo.new_siparisBase
WHERE statecode = 0 AND statuscode = 100000000 AND ISNULL(new_kargotakipno, '') <> '' AND new_sevktarihi >= @bas_utc ORDER BY NEWID();
SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_sevkiyatBase WHERE statecode = 0 AND new_siparisid = @id;
SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_kargotakipbilgisiBase WHERE statecode = 0 AND new_siparisid = @id;
