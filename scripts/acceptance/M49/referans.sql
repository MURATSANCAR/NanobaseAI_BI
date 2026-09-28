-- M49 Veri güvenliği — bağımsız referans sorguları (köprü kodu kullanılmadan; test sunucusunda, salt okunur).
-- Meta veritabanı (PostgreSQL, bi_meta), giriş servisinin SQLite'ı (/var/lib/timas-login/sessions.sqlite) ve CRM
-- (.28, Timas_MSCRM) ayrı yerlerdir; kabul.py her birini kendi bağlantısıyla koşar ve API cevabıyla karşılaştırır.
-- :t0 = kabul başlangıcı (UTC), :tenant / :ds = köprünün tenant ve veri kaynağı.

-- R1 · Giriş kaydı: timasai'nin kabul sırasında yaptığı denemeler iki yerde aynı sayıda.
--   giriş servisi (sqlite, sudo ile):
SELECT count(*) FROM login_events WHERE username = 'timasai' AND at > :t0_epoch;
--   meta DB (köprünün çektiği kopya):
SELECT count(*), sum(CASE WHEN ok THEN 1 ELSE 0 END) FROM semantic_security_logins WHERE username = 'timasai' AND at > :t0;

-- R2 · 403 kaydı: yetkisi olmayan ikinci oturumun finansal denetim denemesi.
SELECT count(*) FROM semantic_security_access
WHERE kind = 'forbidden' AND perm_key = 'sayfa:finansal-denetim' AND at > :t0;

-- R3 · Envanter: katalogda kişisel veri işaretli kolon sayısı (varlık + kolon başına bir) = ekrandaki «Maskeli kolon».
SELECT count(*) FROM (
  SELECT DISTINCT upper(p.entity) AS e, upper(c->>'name') AS col
  FROM sl_schema_profile p, jsonb_array_elements(p.columns_json::jsonb) c
  WHERE p.datasource_id = :ds AND (c->>'sensitive')::boolean
) x;
--   CRM Contact TC sütunu katalogda işaretli mi (işaretli değilse bulgu; düzeltme SEMANTIC_PII_PATTERNS):
SELECT p.entity, c->>'name' AS col, c->>'sensitive' AS sensitive, c->>'sensitivity_reason' AS reason
FROM sl_schema_profile p, jsonb_array_elements(p.columns_json::jsonb) c
WHERE p.datasource_id = :ds AND upper(p.entity) LIKE '%CONTACT%' AND lower(c->>'name') ~ '(tc|kimlik|nufus|vergi)';

-- R4 · Hesap hijyeni: CRM'de etkin etki alanı kullanıcıları (CRM .28, doğrudan). AD etkin listesiyle farkı kabul.py
--   ldap3 ile ayrıca okur; fark = «CRM'de etkin, AD'de etkin değil» sayısı.
SELECT DomainName FROM Timas_MSCRM.dbo.SystemUserBase
WHERE IsDisabled = 0 AND AccessMode IN (0, 1) AND DomainName IS NOT NULL AND DomainName <> '';

-- R5 · Saklama önizlemesi (soru sonucu, N = SECURITY_RETENTION_QUERY_RESULT_DAYS):
SELECT count(*) FROM sl_query_log
WHERE tenant_id = :tenant AND datasource_id = :ds AND created_at < now() - (:n || ' days')::interval AND result_json IS NOT NULL;

-- R6 · Saklama önizlemesi (model sırası metni, N = SECURITY_RETENTION_LLM_TEXT_DAYS):
SELECT (SELECT count(*) FROM sl_llm_queue WHERE enqueued_at < now() - (:n || ' days')::interval
          AND question IS NOT NULL AND status IN ('DONE', 'ABANDONED'))
     + (SELECT count(*) FROM sl_llm_job WHERE created_at < now() - (:n || ' days')::interval
          AND status IN ('DONE', 'FAILED', 'CANCELLED') AND (messages_json <> '[]' OR result IS NOT NULL));

-- R7 · «Herkes»ten sayfa:finansal-denetim çıkarılırsa kaybeden: AD'deki etkin kişilerden, bu sayfayı Herkes dışındaki
--   bir rolden (kişi bağı ya da grup/OU/CRM rolü üyeliği) ALMAYAN ve yönetici olmayanlar. kabul.py bu iki sorgunun
--   sonucunu Python'da kesiştirir (köprünün access modülü kullanılmaz).
SELECT b.subject_type, lower(b.subject) AS subject, m.members
FROM semantic_access_bindings b
JOIN semantic_access_role_perms rp ON rp.role_id = b.role_id AND rp.perm = 'sayfa:finansal-denetim'
LEFT JOIN semantic_access_members m ON m.subject_type = b.subject_type AND m.subject = lower(b.subject)
WHERE b.tenant_id = :tenant
UNION ALL
SELECT b.subject_type, lower(b.subject), m.members
FROM semantic_access_bindings b
JOIN semantic_access_roles r ON r.id = b.role_id AND r.all_perms AND NOT r.is_system
LEFT JOIN semantic_access_members m ON m.subject_type = b.subject_type AND m.subject = lower(b.subject)
WHERE b.tenant_id = :tenant;

-- R8 · Son 24 saat 403 sayısı = özet ekranındaki «Yetkisiz deneme · 24 saat».
SELECT count(*) FROM semantic_security_access WHERE kind = 'forbidden' AND at >= now() - interval '24 hours';
