-- M23 İşbirlikleri — bağımsız referans sorguları (köprü kodu kullanılmadan; test sunucusunda, salt okunur).
-- R1–R3 CRM'de (Timas_MSCRM, .28), R4–R5 portal kataloğunda (Postgres, semantic_infl_*). kabul.py aynı sorguları
-- parametreleri yerine koyarak çalıştırır ve uçların kullanıcıya verdiği sonuçla karşılaştırır.

-- R1 · Tanıtım gönderimi: kişi kartındaki «gönderilen kitap» adedi (kartın CRM sipariş numaralarından).
SELECT SUM(ss.new_adet) AS adet, COUNT(DISTINCT s.new_name) AS siparis
FROM Timas_MSCRM.dbo.new_siparissatiriBase ss
JOIN Timas_MSCRM.dbo.new_siparisBase s ON s.new_siparisId = ss.new_siparisid
WHERE s.new_siparistipi = 12 AND s.new_name IN (/* @kartin_siparis_nolari */ N'');

-- R2 · CRM pazarlama bütçe modülündeki «Influencer» harcaması (dönem; tarih İstanbul günü → UTC sınır, −3 saat).
SELECT SUM(new_tutar) AS toplam, COUNT(*) AS kayit
FROM Timas_MSCRM.dbo.new_pazarlamamoduluBase
WHERE statecode = 0 AND new_mecratipi4 = 6
  AND new_baslangictarihi >= DATEADD(HOUR, -3, CAST(@bas AS datetime))
  AND new_baslangictarihi <  DATEADD(HOUR, -3, DATEADD(DAY, 1, CAST(@bit AS datetime)));

-- R3 · Sosyal kullanıcı adı olan aktif CRM kişileri (kayıt defterine eşleşme önerisi tabanı); yazarlar ayrı.
SELECT COUNT(*) AS kisi, SUM(CASE WHEN ISNULL(new_yazarmi, 0) = 1 THEN 1 ELSE 0 END) AS yazar
FROM Timas_MSCRM.dbo.ContactBase
WHERE statecode = 0 AND (NULLIF(LTRIM(new_Instagram), '') IS NOT NULL OR NULLIF(LTRIM(new_YoutubeKullancAd), '') IS NOT NULL
   OR NULLIF(LTRIM(new_TwitterKullaniciAdi), '') IS NOT NULL);

-- R3b · Aday sırasının kitap bilgisi: tür metni, raf türü, ağırlıklı hedef yaş (ekrandaki profille birebir).
SELECT new_kitapId, new_name, new_turlertext, new_rafturu, new_hedefkitleyasbaslangic, new_hedefkitleyasbitis
FROM Timas_MSCRM.dbo.new_kitapBase WHERE statecode = 0 AND new_kitapId = @kitap;

-- R4 · Rapor: dönem harcaması, etkileşim ve CPE (portal kataloğu). Dönem günü = yayın günü, yoksa planlanan yayın, yoksa
-- kayıt günü. Vazgeçilen iş sayılmaz. CPE = harcama ÷ etkileşim (etkileşim 0 ise yok).
SELECT COUNT(*) AS isbirligi, COALESCE(SUM(fee), 0) AS harcama, COALESCE(SUM(engagement), 0) AS etkilesim,
       COALESCE(SUM(reach), 0) AS erisim,
       CASE WHEN COALESCE(SUM(engagement), 0) > 0 THEN ROUND(SUM(fee) / SUM(engagement), 4) END AS cpe
FROM semantic_infl_collabs
WHERE tenant_id = :tenant AND stage <> 'vazgecildi'
  AND COALESCE(published_at, due_publish, created_day) BETWEEN :bas AND :bit;

-- R5 · Ödeme listesi yalnız ödeme aşamasındaki işleri içerir; ödenen satırın işi kapanmıştır (ikisi de 0 olmalı).
SELECT COUNT(*) FROM semantic_infl_payouts p JOIN semantic_infl_collabs c ON c.id = p.collab_id
WHERE p.status IN ('hazir', 'onayli') AND c.stage <> 'odeme';
SELECT COUNT(*) FROM semantic_infl_payouts p JOIN semantic_infl_collabs c ON c.id = p.collab_id
WHERE p.status = 'odendi' AND c.stage <> 'kapali';

-- R5b · Ödeme listesi ucu (bu ay): açık satırlar + bu ay ödenenler.
SELECT p.status, COUNT(*) AS satir, SUM(p.amount) AS tutar FROM semantic_infl_payouts p
WHERE p.tenant_id = :tenant AND (p.status IN ('hazir', 'onayli') OR (p.status = 'odendi' AND p.paid_at BETWEEN :ay_bas AND :ay_bit))
GROUP BY p.status;
