-- M28 Kurumsal ilişkiler — bağımsız referans sorguları (CRM .28 Timas_MSCRM, yalnız okuma).
-- kabul.py bunları kendi metniyle koşturur; uygulamanın SQL'i (public_affairs_sources.py) yeniden koşturulmaz.
-- <...> yer tutucuları betik doldurur.

-- R1 — il istatistiği (kabul 1): seçilen ilde okul sayısı, öğrenci toplamı, öğrenci sayısı sayıya çevrilemeyen okul.
SELECT COUNT(z.new_ziyaretyerleriId) AS kurum,
       SUM(TRY_CAST(z.new_renciSays AS int)) AS ogrenci,
       SUM(CASE WHEN TRY_CAST(z.new_renciSays AS int) IS NULL THEN 1 ELSE 0 END) AS sayisiz
FROM Timas_MSCRM.dbo.new_ziyaretyerleriBase z
WHERE z.statecode = 0 AND z.new_KurumTipi = 1 AND z.new_ili = '<il guid>';
-- Not: TRY_CAST(N'' AS int) = 0 döner; uygulama NULLIF(...,'') ile boşu «bilinmiyor» sayar. Fark çıkarsa boş metinli
-- satır sayısı ayrıca yazılır (R1b) ve iki sayı karşılaştırılır — hangisinin doğru olduğu kuralı: boş = bilinmiyor.
SELECT COUNT(*) AS bos FROM Timas_MSCRM.dbo.new_ziyaretyerleriBase z
WHERE z.statecode = 0 AND z.new_KurumTipi = 1 AND z.new_ili = '<il guid>' AND LTRIM(RTRIM(z.new_renciSays)) = N'';

-- R2 — tanıtım/bağış/örnek siparişleri (kabul 2–3), yıl İstanbul saatiyle; iptal ve birleştirilmiş siparişler
-- StringMap etiketinden bulunur (uygulama ayardaki kodu kullanır: 100000001, 100000003).
SELECT CAST(s.new_siparistipi AS int) AS tip, COUNT(DISTINCT s.new_siparisId) AS siparis, SUM(ss.new_adet) AS adet
FROM Timas_MSCRM.dbo.new_siparisBase s
JOIN Timas_MSCRM.dbo.new_siparissatiriBase ss ON ss.new_siparisid = s.new_siparisId
WHERE s.new_siparistipi IN (10, 11, 12, 15)
  AND DATEADD(hour, 3, s.new_siparistarihi) >= '<yıl>-01-01' AND DATEADD(hour, 3, s.new_siparistarihi) < '<yıl+1>-01-01'
  AND s.statuscode NOT IN (SELECT m.AttributeValue FROM Timas_MSCRM.dbo.StringMapBase m
                           WHERE m.AttributeName = 'statuscode' AND m.LangId = 1055
                             AND m.ObjectTypeCode = (SELECT TOP 1 e.ObjectTypeCode FROM Timas_MSCRM.dbo.EntityView e WHERE e.Name = 'new_siparis')
                             AND (m.Value LIKE N'%İptal%' OR m.Value LIKE N'%Birleştir%'))
GROUP BY s.new_siparistipi;

-- R3 — «Karar Veren» rolündeki etkin kişi (kabul 4).
SELECT COUNT(*) AS n FROM Timas_MSCRM.dbo.ContactBase WHERE statecode = 0 AND AccountRoleCode = 1;

-- R4 — CRM kişi araması toplamı (ad, kurum adı ya da iş unvanında sözcük).
SELECT COUNT(*) AS n FROM Timas_MSCRM.dbo.ContactBase k
LEFT JOIN Timas_MSCRM.dbo.AccountBase a ON a.AccountId = k.ParentCustomerId
WHERE k.statecode = 0 AND (k.FullName LIKE N'%<sözcük>%' OR a.Name LIKE N'%<sözcük>%' OR k.JobTitle LIKE N'%<sözcük>%');

-- R5 — CRM ziyaret yeri araması toplamı (okul tipi).
SELECT COUNT(*) AS n FROM Timas_MSCRM.dbo.new_ziyaretyerleriBase z
WHERE z.statecode = 0 AND z.new_KurumTipi = 1 AND (z.new_kurumadi LIKE N'%<sözcük>%' OR z.new_okuladi LIKE N'%<sözcük>%');

-- R6 — ayın yeni kitapları (ilk baskı tarihi İstanbul ayı; iptal/ertelenen/devredilen statüler hariç, stok kodu dolu).
SELECT COUNT(*) AS n FROM Timas_MSCRM.dbo.new_kitapBase b
WHERE b.statecode = 0 AND ISNULL(b.new_StokKodu, N'') <> N''
  AND ISNULL(CAST(b.new_kitap_yayincilikstatusu AS int), 0) NOT IN (100000001, 100000003, 100000005, 100000006)
  AND DATEADD(hour, 3, b.new_ilkyayintarihi) >= '<ay başı>' AND DATEADD(hour, 3, b.new_ilkyayintarihi) < '<sonraki ay başı>';

-- P1 — portal: aynı kişiye aynı kitap tekrarı (kabul 5) — boş dönmeli.
SELECT person_id, crm_book_id, COUNT(*) FROM semantic_rel_gifts WHERE status <> 'iptal'
GROUP BY person_id, crm_book_id HAVING COUNT(*) > 1;

-- P2 — portal: alan listesi ve kişi kartında yasak sınıf (kabul 6) — 0 dönmeli.
SELECT COUNT(*) FROM semantic_rel_fields
WHERE lower(label) LIKE '%inanç%' OR lower(label) LIKE '%mezhep%' OR lower(label) LIKE '%cemaat%'
   OR lower(label) LIKE '%siyasi%' OR lower(label) LIKE '%parti%' OR lower(label) LIKE '%etnik%' OR lower(label) LIKE '%sendika%';
