-- M54 Telif dönemi — bağımsız referans sorguları (elle karşılaştırma için; accept.py aynılarını koşturur).
-- CRM: Timas_MSCRM.dbo (.28), Logo: LOGO_DB. Kapsam kodları Yönetim → «Telif dönemi» ayarlarındaki varsayılanlar.

-- 1. Kapsam = koşudaki CRM kaynaklı satır sayısı (hesaplandı + istisna + hariç)
SELECT COUNT(*) AS n FROM Timas_MSCRM.dbo.new_sozlesmeBase s
WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 5 AND s.new_TelifTipi IN (2, 7) AND s.statuscode IN (100000000, 100000007);

-- 2. «Stok kodu yok» istisnası (portalda kaydı olan sözleşmeler hariç tutulur)
SELECT COUNT(DISTINCT s.new_sozlesmeId) AS n FROM Timas_MSCRM.dbo.new_sozlesmeBase s
JOIN Timas_MSCRM.dbo.new_new_sozlesme_new_kitapBase sk ON sk.new_sozlesmeid = s.new_sozlesmeId
JOIN Timas_MSCRM.dbo.new_kitapBase k ON k.new_kitapId = sk.new_kitapid
WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 5 AND s.new_TelifTipi IN (2, 7) AND s.statuscode IN (100000000, 100000007)
  AND k.new_name IS NOT NULL AND ISNULL(k.new_StokKodu, '') = '';

-- 3. Telif doğruluğu: satırın stok kodlarıyla dönem satışı (iade satırlarında adet ve tutar eksi yazılı)
SELECT s.[Malzeme/Hizmet Kodu] AS kod, SUM(s.[Miktar]) AS adet, SUM(s.[Net Tutar]) AS net
FROM dbo.V_SatisRaporu_2026 s
WHERE s.[Satır Türü] = N'Malzeme' AND s.[Yıl] * 12 + s.[Ay] BETWEEN 2026 * 12 + 1 AND 2026 * 12 + 6
  AND s.[Malzeme/Hizmet Kodu] IN (N'<kod1>', N'<kod2>')
GROUP BY s.[Malzeme/Hizmet Kodu];
-- brüt telif = Σ net × oran / 100 (karton oranı; e-kitap kodu e-kitap oranıyla)

-- 4. Koşu toplamı (portal mağazası)
SELECT para, SUM(net) AS net, COUNT(*) AS satir FROM semantic_royalty_run_lines
WHERE run_id = '<kosu>' AND durum = 'hesaplandi' GROUP BY para;
-- onaydan sonra: yeni hakediş sayısı = hesaplandı satır sayısı
SELECT COUNT(*) FROM semantic_royalty_run_lines WHERE run_id = '<kosu>' AND statement_id IS NOT NULL;

-- 5. Yenileme (90 gün)
SELECT COUNT(*) AS n FROM Timas_MSCRM.dbo.new_sozlesmeBase
WHERE statecode = 0 AND ISNULL(new_suresizsozlesme, 0) = 0
  AND new_SozlesmeBitisTarihi >= '<bugun>' AND new_SozlesmeBitisTarihi < DATEADD(day, 90, '<bugun>');

-- 6. Hak kartı: yürürlükteki Telif Alış sözleşmelerinde iletim hakkı olan kitap sayısı (2026-09-26: 6.783 sözleşme)
SELECT COUNT(DISTINCT sk.new_kitapid) AS n FROM Timas_MSCRM.dbo.new_new_sozlesme_new_kitapBase sk
JOIN Timas_MSCRM.dbo.new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid
WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 5 AND s.new_iletimhakki = 1;

-- Ölçülecek doluluklar (analiz §6): yenileme alanları, hak açıklaması, özgün dil, satılan ülke, taraf e-postası
SELECT COUNT(*) AS etkin,
  SUM(CASE WHEN new_SzlemeYenilenmeSklyl IS NOT NULL THEN 1 ELSE 0 END) AS yenileme_sikligi,
  SUM(CASE WHEN new_yenilemebitistarihi IS NOT NULL THEN 1 ELSE 0 END) AS yenileme_bitis,
  SUM(CASE WHEN new_RaporVermeSresi IS NOT NULL THEN 1 ELSE 0 END) AS rapor_suresi,
  SUM(CASE WHEN new_YaynlanmamasHalindeFesihTarihi IS NOT NULL THEN 1 ELSE 0 END) AS yayinlanmama_fesih,
  SUM(CASE WHEN new_orjinaldili IS NOT NULL THEN 1 ELSE 0 END) AS orjinal_dil,
  SUM(CASE WHEN new_telifsatilanulke IS NOT NULL THEN 1 ELSE 0 END) AS satilan_ulke
FROM Timas_MSCRM.dbo.new_sozlesmeBase WHERE statecode = 0;
