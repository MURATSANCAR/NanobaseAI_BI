-- H4 Kurumsal e-posta — bağımsız referans sorguları (kabul.py bunları parametreyle koşturur).
-- CRM (Timas_MSCRM, .28) yalnız okunur. Köprü tabloları bi_meta (Postgres).

-- R1 Gönderen tanıma: kişi / firma / aday, etkin kayıt, tam eşleşme (küçük harf, kırpılmış). :adres kutudan anlık okunur.
SELECT TOP 1 CAST(ContactId AS nvarchar(40)) AS id FROM Timas_MSCRM.dbo.ContactBase
 WHERE StateCode = 0 AND LOWER(LTRIM(RTRIM(EMailAddress1))) = LOWER(:adres) ORDER BY CAST(ContactId AS nvarchar(40));
SELECT TOP 1 CAST(AccountId AS nvarchar(40)) AS id FROM Timas_MSCRM.dbo.AccountBase
 WHERE StateCode = 0 AND LOWER(LTRIM(RTRIM(EMailAddress1))) = LOWER(:adres) ORDER BY CAST(AccountId AS nvarchar(40));
SELECT TOP 1 CAST(LeadId AS nvarchar(40)) AS id FROM Timas_MSCRM.dbo.LeadBase
 WHERE StateCode = 0 AND LOWER(LTRIM(RTRIM(EMailAddress1))) = LOWER(:adres) ORDER BY CAST(LeadId AS nvarchar(40));

-- R1b (ölçülecek) E-posta doluluğu: tanıma oranının üst sınırı.
SELECT COUNT(*) AS kisi, SUM(CASE WHEN EMailAddress1 IS NOT NULL AND EMailAddress1 <> '' THEN 1 ELSE 0 END) AS epostali
  FROM Timas_MSCRM.dbo.ContactBase WHERE StateCode = 0;

-- R1c (ölçülecek) Olası yazar bağı kolonu gerçekten var mı (analizdeki ad: new_olasyazaryazar).
SELECT COLUMN_NAME FROM Timas_MSCRM.INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME = 'new_projeBase' AND COLUMN_NAME = 'new_olasyazaryazar';

-- R2 Yönlendirme hedefi CRM'de etkin kullanıcı (:hesap = AD sAMAccountName).
SELECT COUNT(*) AS v FROM Timas_MSCRM.dbo.SystemUserBase
 WHERE IsDisabled = 0 AND LOWER(DomainName) = LOWER(N'timas\' + :hesap);

-- R3 Hacim (portal tarafı): son 7 gün. Kutu tarafı Gmail `after:<epoch> -in:sent -in:drafts -in:chats`, spam dahil.
SELECT COUNT(*) FROM semantic_mail_messages WHERE tenant_id = :t AND received_at >= now() - interval '7 days';

-- R4 İlk yanıt ortalaması (takvim saati) tür bazında; rapor ekranındaki «İlk yanıt (takvim)» ile aynı olmalı.
SELECT COALESCE(category, '-') AS tur, AVG(EXTRACT(EPOCH FROM (first_reply_at - received_at)) / 3600.0) AS saat, COUNT(*) AS n
  FROM semantic_mail_messages
 WHERE tenant_id = :t AND historical = false AND received_at >= :bas AND first_reply_at IS NOT NULL
 GROUP BY 1;

-- R5 Doğruluk: insan etiketi ile modelin ilk seçimi (çoğunluk kabul.py'de; burada ham uyuşma).
SELECT l.category_key AS insan, m.model_category AS model, COUNT(*) AS n
  FROM semantic_mail_labels l JOIN semantic_mail_messages m ON m.id = l.message_id
 WHERE l.tenant_id = :t GROUP BY 1, 2 ORDER BY 3 DESC;

-- R6 Portal adına yanıt olmamalı (otomatik yanıt bu sürümde yok).
SELECT COUNT(*) FROM semantic_mail_events WHERE action = 'yanitlandi' AND "by" IN ('sistem', 'zeki');

-- R7 Aynı ileti iki kez kaydedilmemeli.
SELECT tenant_id, provider, provider_id, COUNT(*) FROM semantic_mail_messages GROUP BY 1, 2, 3 HAVING COUNT(*) > 1;

-- R8 Aktarılan başvurunun CRM proje bağı (insan eşlediyse).
SELECT new_projeId FROM Timas_MSCRM.dbo.new_projeBase WHERE new_projeId = :crm_project_id;
