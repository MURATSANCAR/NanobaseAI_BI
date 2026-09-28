-- M56 Performans — bağımsız referans sorguları (uygulamanın SQL'i yeniden koşturulmaz; tanım analiz §14'ten).
-- Logo 2026 = LG_411 (bellek: logo-period-prefixes-are-years); .155 kopyası 2026-08-17'de donmuş.

-- K1 Satış temsilcisi alanı doluluğu (ölçüm; sistem ölçüsünü açma kararı buna bağlı)
SELECT COUNT(*) AS satir, SUM(CASE WHEN i.SALESMANREF <> 0 THEN 1 ELSE 0 END) AS temsilcili
FROM LG_411_01_INVOICE i WHERE i.CANCELLED = 0 AND i.TRCODE IN (7,8,9)
  AND i.DATE_ >= '2026-01-01' AND i.DATE_ < '2027-01-01';

-- K2 Temsilci bazında faturalı net satış (satış − iade, LINENET)
SELECT s.CODE, SUM(CASE WHEN l.TRCODE IN (7,8,9) THEN l.LINENET WHEN l.TRCODE IN (2,3) THEN -l.LINENET ELSE 0 END) AS net
FROM LG_411_01_STLINE l
JOIN LG_411_01_INVOICE i ON i.LOGICALREF = l.INVOICEREF
JOIN LG_411_SLSMAN s ON s.LOGICALREF = i.SALESMANREF
WHERE l.CANCELLED = 0 AND l.LINETYPE = 0 AND l.INVOICEREF <> 0
  AND l.DATE_ >= '2026-01-01' AND l.DATE_ < '2026-08-18'
GROUP BY s.CODE;

-- K3 CRM kişi ↔ Logo temsilcisi köprüsü (ölçüm; kesişim Python'da)
SELECT COUNT(*) FROM Timas_MSCRM.dbo.SystemUserBase u WHERE u.IsDisabled = 0 AND u.new_KullancKoduLogoyaGnderilen IS NOT NULL;
SELECT CODE FROM LG_411_SLSMAN;

-- K4 Editör iş özeti (bi_meta Postgres)
SELECT COUNT(*) FROM semantic_editorial_tasks
WHERE tenant_id = :t AND lower(editor_id) = lower(:crm_id) AND status = 'tamamlandi' AND done_at >= :bas AND done_at < :son_arti_1;
-- termininde: aynı sorgu + AND due_date IS NOT NULL AND done_at::date <= due_date

-- K5 CRM proje ve sözleşme sahipliği
SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_projeBase WHERE OwnerId = :systemuserid AND CreatedOn >= :bas AND CreatedOn < :son_arti_1;
SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_sozlesmeBase WHERE OwnerId = :systemuserid AND CreatedOn >= :bas AND CreatedOn < :son_arti_1;

-- K6 Dönem tamamlanma
SELECT COUNT(*) FILTER (WHERE self_submitted_at IS NOT NULL) * 1.0 / COUNT(*),
       COUNT(*) FILTER (WHERE manager_submitted_at IS NOT NULL) * 1.0 / COUNT(*)
FROM semantic_hr_reviews WHERE cycle_id = :c;

-- K7 Kapsam: yöneticinin ekibi (manager_id zinciri)
WITH RECURSIVE ekip AS (
  SELECT id FROM semantic_hr_employees WHERE tenant_id = :t AND manager_id = :yonetici
  UNION
  SELECT e.id FROM semantic_hr_employees e JOIN ekip ON e.manager_id = ekip.id WHERE e.tenant_id = :t
) SELECT id FROM ekip;

-- K8 Hiyerarşi doluluğu
SELECT COUNT(*) FILTER (WHERE manager_id IS NULL) FROM semantic_hr_employees WHERE tenant_id = :t AND status = 'aktif';
