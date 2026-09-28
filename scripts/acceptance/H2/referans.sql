-- H2 Okuyucu veri tabanı — doğrudan CRM referans sorguları (CRM prod .28, yalnız okuma).
-- kabul.py bunları köprü kodu kullanmadan koşturur ve uçların verdiği sayılarla karşılaştırır.
-- Şema: Timas_MSCRM.dbo (CRM_SCHEMA ile değişir).

-- R1 · Etkin kişi kartı = «CRM kişi» kaynağının okunan satırı (Özet → Kaynak tazeliği).
SELECT COUNT(*) AS n FROM Timas_MSCRM.dbo.ContactBase WHERE StateCode = 0;

-- R2 · Form tipi kırılımı (NULL = «bos») = özet ekranındaki «CRM kişi kartı: form tipi».
SELECT new_geliskanali AS kod, COUNT(*) AS n FROM Timas_MSCRM.dbo.ContactBase WHERE StateCode = 0 GROUP BY new_geliskanali;

-- R3 · Açık müşteri adayı = «CRM müşteri adayı» kaynağının okunan satırı (READERS_LEAD_STATES varsayılan 0).
SELECT COUNT(*) AS n FROM Timas_MSCRM.dbo.LeadBase WHERE StateCode = 0;

-- R4 · E-postalı tekil kişi+aday (portal aynı normalizasyonu kullanır: baş/son boşluk, küçük harf, «@» içerir).
SELECT COUNT(DISTINCT LOWER(LTRIM(RTRIM(e)))) AS n FROM (
  SELECT EMailAddress1 e FROM Timas_MSCRM.dbo.ContactBase WHERE StateCode = 0
  UNION ALL SELECT EMailAddress1 FROM Timas_MSCRM.dbo.LeadBase WHERE StateCode = 0) x
WHERE e LIKE '%@%';

-- R5 · İYS son durum: her (müşteri, entegrasyon alanı) için en son kayıt; alan × durum sayısı.
WITH son AS (
  SELECT obs_customerid, obs_iysintegrationfieldid, obs_permissionstatus,
         ROW_NUMBER() OVER (PARTITION BY obs_customerid, obs_iysintegrationfieldid
                            ORDER BY obs_permissiondate DESC, CreatedOn DESC) rn
  FROM Timas_MSCRM.dbo.obs_iyslogBase WHERE ISNULL(obs_iserror, 0) = 0)
SELECT obs_iysintegrationfieldid AS alan, obs_permissionstatus AS durum, COUNT(*) AS n
FROM son WHERE rn = 1 GROUP BY obs_iysintegrationfieldid, obs_permissionstatus;

-- R6 · E-posta engeli: bu kişilerin hiçbiri e-posta listesine giremez (portalın okur/izin tablosuyla karşılaştırılır).
SELECT ContactId AS id FROM Timas_MSCRM.dbo.ContactBase WHERE StateCode = 0 AND (DoNotEMail = 1 OR DoNotBulkEMail = 1);

-- R7 · Etkinlik katılımı olan kişi = özetteki «CRM etkinliğine katılan kişi».
SELECT COUNT(DISTINCT contactid) AS n FROM Timas_MSCRM.dbo.new_new_etkinlik_contactBase;

-- R8 · Kampanya geçmişi = özetteki «CRM kampanya geçmişi».
SELECT Name AS ad, obs_totalcount AS gonderim, obs_readcount AS okunma, obs_clickcount AS tiklama FROM Timas_MSCRM.dbo.CampaignBase;

-- R9 · Okur sayılmayan kişi kartı: kuruma bağlı / (kuruma bağlı değil ve) esere katkı veren.
SELECT
  SUM(CASE WHEN ParentCustomerId IS NOT NULL THEN 1 ELSE 0 END) AS kurum,
  SUM(CASE WHEN ParentCustomerId IS NULL AND ContactId IN (
        SELECT new_Katilimsaglayan FROM Timas_MSCRM.dbo.new_eserkatilimBase WHERE statecode = 0) THEN 1 ELSE 0 END) AS katki
FROM Timas_MSCRM.dbo.ContactBase WHERE StateCode = 0;

-- R10 · Hatasız İYS günlük satırı = okunan İYS satırı.
SELECT COUNT(*) AS n FROM Timas_MSCRM.dbo.obs_iyslogBase WHERE ISNULL(obs_iserror, 0) = 0;
