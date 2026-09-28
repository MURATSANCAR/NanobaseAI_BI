-- M24 Katalog ve bülten — bağımsız referans sorguları (köprü kodu kullanılmadan; test sunucusunda, salt okunur).
-- CRM (.28, Timas_MSCRM) ve Logo ayrı sunuculardır; tek sorguda birleşmez, stok koduyla birleştirilir.
-- @... yer tutucularını kabul.py koşu sırasında rastgele seçilen kayıtlarla doldurur (sabit kitap/kişi yok).

-- R1 · Stok ay sayısı = CRM stok adedi ÷ ağırlıklı aylık satış hızı (Baskı önerisi «Tükenme süresi»).
--   Stok adedi (Baskı önerisi crm_kitap kaynağıyla aynı görünüm):
SELECT StokKodu, StokAdedi FROM Timas_MSCRM.dbo.powerbikitap WHERE StokKodu IN (@stok_kodlari);
--   Satış hızı: management/sql/baski_oneri/logo_satis_hizi.sql, {satis:2024} yıllık görünümlere açılmış hâliyle,
--   yalnız seçilen kodlar için (kabul.py metni dosyadan okur, köprü koduna dokunmaz).
--   Ayrıca Yönetim raporları › Baskı önerisi ekranındaki (Baskı Tekrar) «Tükenme süresi» ile karşılaştırılır.

-- R2 · Katalog fiyatı (kaynak CRM kitap kartı, KDV dahil).
SELECT new_kitapId, new_kdvdahilfiyat FROM Timas_MSCRM.dbo.new_kitapBase WHERE new_kitapId IN (@kitap_idleri);

-- R3 · Segment sayısı: izinli ve tarih ilgili kişi. Ekrandaki sayı ile birebir.
SELECT COUNT(DISTINCT c.ContactId) AS izinli
FROM Timas_MSCRM.dbo.ContactBase c
WHERE c.statecode = 0 AND ISNULL(c.DoNotBulkEMail,0) = 0 AND ISNULL(c.DoNotEMail,0) = 0 AND c.new_iysonayi = 1
  AND NULLIF(LTRIM(c.EMailAddress1),'') IS NOT NULL AND c.new_tarihveakademi = 1;
-- R3b · İzin alanlarından biri eksik olan tarih ilgili kişi (sayıya GİRMEMELİ): ekrandaki «izin kuralına takılan».
SELECT COUNT(*) FROM Timas_MSCRM.dbo.ContactBase c
WHERE c.statecode = 0 AND c.new_tarihveakademi = 1
  AND NOT (ISNULL(c.DoNotBulkEMail,0) = 0 AND ISNULL(c.DoNotEMail,0) = 0 AND c.new_iysonayi = 1
           AND NULLIF(LTRIM(c.EMailAddress1),'') IS NOT NULL);

-- R4 · Özel güne bağlı kitap sayısı (SEO Sezon takvimi kabulündeki sorgu).
SELECT o.new_name, COUNT(DISTINCT l.new_kitapid) AS kitap
FROM Timas_MSCRM.dbo.new_new_kitap_new_ozelgunlerBase l
JOIN Timas_MSCRM.dbo.new_kitapBase k ON k.new_kitapId = l.new_kitapid
JOIN Timas_MSCRM.dbo.new_ozelgunlerBase o ON o.new_ozelgunlerId = l.new_ozelgunlerid
WHERE k.statecode = 0 AND k.new_ean13 IS NOT NULL AND o.statecode = 0
GROUP BY o.new_name;

-- R5 · CRM kampanya sonucu.
SELECT CampaignId, obs_totalcount, obs_readcount, obs_clickcount FROM Timas_MSCRM.dbo.CampaignBase;

-- R6 · Satıştan kalkan kitaplar (öneriye girmez): yayıncılık statüsü İptal/Bizim değil/Devredildi/Çekildi/Geri istendi
--       ya da satış durumu kapalı; havuz tipleri (varsayılan 1 Kitap, 4 Set).
SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_kitapBase k
LEFT JOIN Timas_MSCRM.dbo.StringMap sm ON sm.AttributeName = 'new_kitap_yayincilikstatusu' AND sm.LangId = 1055
  AND sm.AttributeValue = k.new_kitap_yayincilikstatusu
  AND sm.ObjectTypeCode IN (SELECT e.ObjectTypeCode FROM Timas_MSCRM.MetadataSchema.Entity e WHERE e.Name = 'new_kitap')
WHERE k.statecode = 0 AND k.new_Tip IN (1,4)
  AND (LEFT(sm.Value, 4) IN ('YS01','YS05','YS06','YS11','YS12') OR k.new_satisdurumu = 0);

-- R7 · Logo verisinin son günü (ekrandaki «stok verisi şu tarihe kadar»); firma yıla göre L_CAPIPERIOD'dan.
SELECT MAX(DATE_) FROM dbo.LG_411_01_STLINE WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8,9);

-- R8 · Kişi verisi dışarı çıkmıyor: kabul.py bütün uç yanıtlarında «@» arar (e-posta adresi yok).
