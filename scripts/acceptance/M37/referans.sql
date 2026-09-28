-- M37 Okur topluluğu — bağımsız referans sorguları (test sunucusunda, gerçek CRM .28 üzerinde; yalnız okuma).
-- kabul.py bu sorguları kendi parametreleriyle koşturur; burada elle koşturmak için {yer tutucu}lu hâlleri durur.
-- Okur sayıları (R1–R5) H2 okur veri tabanından gelir: M37 ekranındaki sayı = H2'nin verdiği sayı = bu SQL zinciri sınanır.
-- H2 bağlı değilse R1–R5 «DOĞRULANAMADI» yazılır; R6–R8 M37'nin kendi kaynağıdır ve her zaman koşar.

-- R1. Kayıt tipi dağılımı (analiz §14 kabul 1). Ekran: /overview → envanter.satirlar (kaynak «CRM kişi», kayitTipi).
SELECT new_kayittipi AS kayit_tipi, COUNT(*) AS sayi
FROM Timas_MSCRM.dbo.ContactBase WHERE statecode = 0 GROUP BY new_kayittipi;
-- Not: H2 okur/katkıcı ayrımı yapıyorsa ekran R1'den küçük olur; fark kabulde sayıyla yazılır (ölçülecek: okur ayrım kuralı).

-- R2. İzin oranları (kabul 2). Ekran: envanter satırlarının kvkkOnayli / iysOnayli / epostaIzinli toplamı (CRM kişi).
SELECT COUNT(*) AS toplam,
       SUM(CASE WHEN new_kvkkonayi = 1 THEN 1 ELSE 0 END) AS kvkk,
       SUM(CASE WHEN new_iysonayi = 1 THEN 1 ELSE 0 END) AS iys,
       SUM(CASE WHEN ISNULL(DoNotEMail, 0) = 0 THEN 1 ELSE 0 END) AS eposta_engelsiz
FROM Timas_MSCRM.dbo.ContactBase WHERE statecode = 0;

-- R3. İzin çelişkisi «İYS onayı yok ama kampanya gönderimi var» (kabul 3). Ekran: /consent-health → items[tur = M37_CELISKI_TUR].
SELECT COUNT(DISTINCT g.obs_kisiid) AS sayi
FROM Timas_MSCRM.dbo.obs_kampanyagonderimleriBase g
JOIN Timas_MSCRM.dbo.ContactBase c ON c.ContactId = g.obs_kisiid
WHERE ISNULL(c.new_iysonayi, 0) = 0;

-- R4. Okur adayı kaynak tablosu (kabul 4). Ekran: envanter satırları (kaynak «CRM aday»).
SELECT obs_mainsourcename AS kaynak, COUNT(*) AS sayi, SUM(CASE WHEN obs_donotkvkk = 1 THEN 1 ELSE 0 END) AS kvkk_ret
FROM Timas_MSCRM.dbo.LeadBase GROUP BY obs_mainsourcename;

-- R5. Segment önizlemesi (kabul 5): kabul segmentinin kuralı elle yazılmış SQL ile sayılır. Varsayılan kural «bir ilgi alanı»
-- (H2'nin ilgi alanı kimliği CRM new_kitapilgialan kimliğiyse). N:N kolon adları ölçülecek; M37_R5_SQL ile değiştirilebilir.
SELECT COUNT(DISTINCT c.ContactId) AS toplam,
       COUNT(DISTINCT CASE WHEN c.new_kvkkonayi = 1 AND ISNULL(c.DoNotEMail, 0) = 0 THEN c.ContactId END) AS eposta_izinli
FROM Timas_MSCRM.dbo.new_contact_new_kitapilgialanBase b
JOIN Timas_MSCRM.dbo.ContactBase c ON c.ContactId = b.contactid
WHERE c.statecode = 0 AND b.new_kitapilgialanid = '{ilgi_id}';

-- R6. Geçmiş etkinlik özeti (kabul 6). Ekran: /events-summary?yil={yil} → tamamlanan, katilimci, satilan.
-- Okul/cari ziyareti (new_ziyarettipi dolu) dışarıda (OKUR_ETKINLIK_ZIYARET_HARIC=1); tip süzgeci boş.
SELECT COUNT(*) AS etkinlik, SUM(new_katilimcisayisi) AS katilimci, SUM(new_SatilanKitapAd) AS satilan
FROM Timas_MSCRM.dbo.new_etkinlikBase
WHERE statuscode = 100000002 AND new_ziyarettipi IS NULL
  AND new_BalangTarihi >= '{yil}-01-01' AND new_BalangTarihi < '{yil+1}-01-01';

-- R6b. Aynı yılın bütün durumları (ekran: toplam ve durumlar).
SELECT CAST(statuscode AS int) AS durum, COUNT(*) AS sayi
FROM Timas_MSCRM.dbo.new_etkinlikBase
WHERE new_ziyarettipi IS NULL AND new_BalangTarihi >= '{yil}-01-01' AND new_BalangTarihi < '{yil+1}-01-01'
GROUP BY statuscode;

-- R7. Etkinlik tipine göre tamamlanan (ekran: tipler).
SELECT ISNULL(t.new_name, '(tipsiz)') AS tip, COUNT(*) AS etkinlik, SUM(e.new_SatilanKitapAd) AS satilan
FROM Timas_MSCRM.dbo.new_etkinlikBase e
LEFT JOIN Timas_MSCRM.dbo.new_etkinliktipiBase t ON t.new_etkinliktipiId = e.new_etkinliktipiid
WHERE e.statuscode = 100000002 AND e.new_ziyarettipi IS NULL
  AND e.new_BalangTarihi >= '{yil}-01-01' AND e.new_BalangTarihi < '{yil+1}-01-01'
GROUP BY t.new_name;

-- R8. Yorumlar (kabul 7): SEO gece özeti toplamı (katalog veritabanı, SEMANTIC_STORE_DSN). Ekran: /reviews → sayilar.toplam
-- (anlık T-soft okuması; gece ile arada yeni yorum gelebilir, fark sayıyla yazılır). 2026-09-25: 86 yorum, 67 ürün.
-- SELECT SUM(comments), COUNT(*) FROM semantic_seo_reviews WHERE tenant_id = '{tenant}';
