-- M36 Dijital yayın ve e-kitap — bağımsız referans sorguları (doğrudan bağlantıyla; uygulamanın SQL'i değildir).
-- CRM: canlı 192.168.0.28 Timas_MSCRM.dbo (yalnız okuma). Logo: köprünün bağlantısı; yıl → firma L_CAPIPERIOD'dan.
-- kabul.py bu sorguları aynı biçimde koşturur; burada elle bakmak için durur.

-- K1 Tip sayıları (katalog göstergesi «e-kitap kaydı» / «sesli kitap kaydı»)
SELECT new_Tip, COUNT(*) AS sayi FROM Timas_MSCRM.dbo.new_kitapBase WHERE statecode = 0 AND new_Tip IN (8, 9) GROUP BY new_Tip;

-- K2 Sözleşme düzeyi haklar: yürürlük durumundaki Telif Alış sözleşmeleri (2026-09-26: e-kitap 6.629, iletim 6.783)
SELECT COUNT(*) AS yururlukte,
       SUM(CASE WHEN new_EKitap = 1 THEN 1 ELSE 0 END) AS ekitap,
       SUM(CASE WHEN new_SesliKitapHakki = 1 THEN 1 ELSE 0 END) AS sesli,
       SUM(CASE WHEN new_iletimhakki = 1 THEN 1 ELSE 0 END) AS iletim
FROM Timas_MSCRM.dbo.new_sozlesmeBase
WHERE new_SozlesmeTipi = 5 AND statuscode IN (100000000, 100000006, 100000007);

-- K3 CRM'de «E-Pub: Evet»
SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_kitapBase WHERE statecode = 0 AND new_EPubDurumu = 1;

-- K4 Fırsat girdisi: Tip = 1, e-kitap stok kodu boş, son 12 takvim ayı (veri sonunun ayı dahil) faturalı net adet.
-- Hak kararı (yürürlükteki bütün Telif Alış sözleşmelerinde new_EKitap = 1, hak notu yok) kabul.py'de Python'da.
SELECT new_kitapId, new_StokKodu FROM Timas_MSCRM.dbo.new_kitapBase
WHERE statecode = 0 AND new_Tip = 1 AND ISNULL(new_EKitapStokKodu, '') = '';
-- Logo (her yıl kendi firmasında; <firma> = L_CAPIPERIOD'dan, <ilk> ve <son> = Yıl*12+Ay sınırları):
SELECT I.CODE, SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet
FROM dbo.LG_<firma>_01_STLINE S JOIN dbo.LG_<firma>_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND YEAR(S.DATE_) * 12 + MONTH(S.DATE_) BETWEEN <ilk> AND <son>
GROUP BY I.CODE;

-- K5 Logo'da e-kitap satışı (e-kitap stok kodlarıyla; kod listesi JOIN (VALUES …) ile — IN listesi planı bozar)
SELECT it.CODE, SUM(s.AMOUNT) AS adet, SUM(s.LINENET) AS net
FROM dbo.LG_<firma>_01_STLINE s JOIN dbo.LG_<firma>_ITEMS it ON it.LOGICALREF = s.STOCKREF
JOIN (VALUES (N'<kod1>'), (N'<kod2>')) v(kod) ON v.kod = it.CODE
WHERE s.TRCODE IN (7,8,9) AND s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0
GROUP BY it.CODE;

-- K7 Hak notu olan Telif Alış sözleşmeleri (2026-09-26: 738)
SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_sozlesmeBase WHERE new_SozlesmeTipi = 5 AND ISNULL(new_haklaraciklama, '') <> '';

-- Ö1 Sesli kitap hakkı olan yürürlükteki sözleşme (analizde «ölçülecek»)
SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_sozlesmeBase
WHERE new_SozlesmeTipi = 5 AND statuscode IN (100000000, 100000006, 100000007) AND new_SesliKitapHakki = 1;

-- Ö2 Dijital kimlik doluluğu (Tip = 1)
SELECT COUNT(*) AS kitap,
       SUM(CASE WHEN ISNULL(new_ekitapisbn, '') <> '' THEN 1 ELSE 0 END) AS e_isbn,
       SUM(CASE WHEN ISNULL(new_EKitapBarkod, '') <> '' THEN 1 ELSE 0 END) AS e_barkod,
       SUM(CASE WHEN ISNULL(new_EKitapStokKodu, '') <> '' THEN 1 ELSE 0 END) AS e_stok
FROM Timas_MSCRM.dbo.new_kitapBase WHERE statecode = 0 AND new_Tip = 1;

-- Ö3 E-kitap üretim aşamasındaki üretim kartları
SELECT statuscode, COUNT(*) FROM Timas_MSCRM.dbo.new_UretimBase WHERE statuscode IN (100000011, 100000012) GROUP BY statuscode;
