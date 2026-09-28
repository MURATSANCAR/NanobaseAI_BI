-- M55 İşe alım + İK-0 — bağımsız referans sorguları (kabul.py bunları koşturur; elle de koşturulabilir).
-- CRM: prod 192.168.0.28, şema admin.conf CRM_SCHEMA (varsayılan Timas_MSCRM.dbo). Yalnız okuma.
-- Köprü: bi_meta Postgres (SEMANTIC_STORE_DSN), :t = SEMANTIC_TENANT_ID.

-- K1 CRM'de etkin (etkileşimli) kullanıcı — eşitleme önizlemesi stats.crmInteractive
SELECT COUNT(*) FROM Timas_MSCRM.dbo.SystemUserBase
 WHERE IsDisabled = 0 AND AccessMode IN (0, 1) AND DomainName IS NOT NULL AND DomainName <> '';
-- K1 bilgi: analizdeki TIMAS\ alan adı süzgeci
SELECT COUNT(*) FROM Timas_MSCRM.dbo.SystemUserBase WHERE IsDisabled = 0 AND AccessMode IN (0, 1) AND DomainName LIKE 'TIMAS\%';
-- K1b devre dışı olmayan bütün hesaplar — stats.crmEnabled
SELECT COUNT(*) FROM Timas_MSCRM.dbo.SystemUserBase WHERE IsDisabled = 0;

-- K2 etkin birim başına devre dışı olmayan kullanıcı — units[].enabledUsers
SELECT b.BusinessUnitId, b.Name, COUNT(*) FROM Timas_MSCRM.dbo.SystemUserBase u
  JOIN Timas_MSCRM.dbo.BusinessUnitBase b ON b.BusinessUnitId = u.BusinessUnitId
 WHERE u.IsDisabled = 0 AND b.IsDisabled = 0 GROUP BY b.BusinessUnitId, b.Name;
-- K2 bilgi: pasif birimdeki etkin kullanıcı (portalda birimsiz kalır)
SELECT COUNT(*) FROM Timas_MSCRM.dbo.SystemUserBase u JOIN Timas_MSCRM.dbo.BusinessUnitBase b ON b.BusinessUnitId = u.BusinessUnitId
 WHERE u.IsDisabled = 0 AND b.IsDisabled = 1;

-- K3 yöneticisi bilinen birim — stats.units / stats.unitsWithManager (kolon HR_CRM_UNIT_MANAGER_COLUMN; doluluk ölçülecek)
SELECT COUNT(*) AS birim, SUM(CASE WHEN new_departmanyoneticisiid IS NOT NULL THEN 1 ELSE 0 END) AS yoneticili
  FROM Timas_MSCRM.dbo.BusinessUnitBase WHERE IsDisabled = 0;

-- K4 ekip başına etkin üye — teams[].members
SELECT t.TeamId, t.Name, COUNT(*) FROM Timas_MSCRM.dbo.TeamMembership m
  JOIN Timas_MSCRM.dbo.TeamBase t ON t.TeamId = m.TeamId
  JOIN Timas_MSCRM.dbo.SystemUserBase u ON u.SystemUserId = m.SystemUserId
 WHERE u.IsDisabled = 0 GROUP BY t.TeamId, t.Name;

-- K5 pano: pozisyon × aşama sayıları (imha edilmemiş adaylar) — /api/v1/hr/recruit/pipeline columns
SELECT COALESCE(position_id, '-') AS p, stage, COUNT(*) FROM semantic_hr_candidates
 WHERE tenant_id = :t AND purged_at IS NULL GROUP BY COALESCE(position_id, '-'), stage;
-- K5b eşik üstü bekleyen (eşik HR_RECRUIT_SLA_DAYS)
SELECT COUNT(*) FROM semantic_hr_candidates WHERE tenant_id = :t AND purged_at IS NULL AND stage <> 'sonuc'
   AND stage_since < now() - make_interval(days => :esik);

-- K6 imha: işten önce ve sonra; tutanak
SELECT COUNT(*) FROM semantic_hr_candidates WHERE tenant_id = :t AND retention_until < now() AND purged_at IS NULL;
SELECT data_class, purged_count, at FROM semantic_hr_purge_runs WHERE tenant_id = :t ORDER BY id DESC LIMIT 5;

-- K7 model izi: İK çağrılarının sıra kaydında yalnız etiket (saklama süresi ölçülecek)
SELECT purpose, question, enqueued_at FROM sl_llm_queue WHERE purpose LIKE '%ik%' ORDER BY enqueued_at DESC LIMIT 5;

-- Ölçüm (kodlamadan önce istenmişti; sonuçlar analiz belgesine işlenecek) — Logo, salt okunur
SELECT COUNT(*) FROM LG_411_EMPLOYEE;
SELECT COUNT(*) FROM LG_411_EMPGROUP;
SELECT COUNT(*) FROM LG_411_SLSMAN WHERE ACTIVE = 0;
SELECT COUNT(*) FROM LG_411_EMPLOYEE WHERE PERSCARDREF > 0;
SELECT name FROM sys.databases;
