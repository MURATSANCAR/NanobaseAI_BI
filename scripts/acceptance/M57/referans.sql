-- M57 Eğitim ve gelişim — bağımsız referans sorguları (kabul.py bunları koşturur; elle de koşturulabilir).
-- Logo: köprünün bağlantı dosyası (SemanticSettings.connection_file), yalnız okuma. Yıl → firma L_CAPIPERIOD'dan.
-- Köprü: bi_meta Postgres (SEMANTIC_STORE_DSN), :t = SEMANTIC_TENANT_ID.

-- R1 (ölçüm, kodlamadan önce) Eğitim gider hesabı adayları — GET /spend/accounts
SELECT CODE, DEFINITION_ FROM LG_411_EMUHACC
 WHERE CODE LIKE '7%' AND (DEFINITION_ LIKE N'%eğitim%' OR DEFINITION_ LIKE N'%EĞİTİM%' OR DEFINITION_ LIKE N'%egitim%'
       OR DEFINITION_ LIKE N'%EGITIM%' OR DEFINITION_ LIKE N'%seminer%' OR DEFINITION_ LIKE N'%SEMİNER%' OR DEFINITION_ LIKE N'%kurs%'
       OR DEFINITION_ LIKE N'%KURS%')
 ORDER BY CODE;

-- R2 Eğitim gideri (yıl) — GET /spend?year=2026 total. Kural 16: SUM(DEBIT − CREDIT), CANCELLED = 0; hesap = ayardaki kod
-- ya da alt hesabı; dönem sonu kapanış fişleri (aynı fişte 7x1 yansıtma hesabına borç satırı olan fişler) hariç.
-- 2026 kopyası 2026-08-17'de bitiyor; 2021–2025 için LG_211_01_EMFLINE / LG_211_EMUHACC ve yıl aralığı.
SELECT SUM(l.DEBIT - l.CREDIT)
  FROM LG_411_01_EMFLINE l
  JOIN LG_411_EMUHACC a ON a.LOGICALREF = l.ACCOUNTREF
 WHERE l.CANCELLED = 0
   AND (a.CODE IN (:egitim_hesaplari) OR a.CODE LIKE :egitim_hesabi_alt)          -- her kod için «kod» ve «kod.%»
   AND l.DATE_ >= '2026-01-01' AND l.DATE_ < '2027-01-01'
   AND l.ACCFICHEREF NOT IN (
       SELECT k.ACCFICHEREF FROM LG_411_01_EMFLINE k JOIN LG_411_EMUHACC ka ON ka.LOGICALREF = k.ACCOUNTREF
        WHERE k.CANCELLED = 0 AND k.SIGN = 0
          AND SUBSTRING(ka.CODE, 1, 3) IN ('711','721','731','741','751','761','771','781','791'));

-- R3 ZEKİ soru kullanımı — usage-map totals["zeki-soru"] (son 30 gün farklı kişi; hesap adı alan adı/e-posta ekinden arındırılır)
SELECT COUNT(DISTINCT lower(split_part(regexp_replace(username, '^.*\\', ''), '@', 1)))
  FROM sl_query_log
 WHERE tenant_id = :t AND username IS NOT NULL AND username <> '' AND created_at >= now() - interval '30 days';
-- R3b birim kırılımı (etkin çalışan kaydıyla)
SELECT e.unit_id, COUNT(DISTINCT e.username)
  FROM sl_query_log q JOIN semantic_hr_employees e
    ON e.tenant_id = q.tenant_id AND e.status = 'aktif'
   AND e.username = lower(split_part(regexp_replace(q.username, '^.*\\', ''), '@', 1))
 WHERE q.tenant_id = :t AND q.created_at >= now() - interval '30 days'
 GROUP BY e.unit_id;

-- R4 Değişiklik kaydı kullanımı — usage-map totals["audit:<tür>"] (sistem ve e-posta aktarımı kişi değildir)
SELECT kind, COUNT(DISTINCT lower(split_part(regexp_replace(actor, '^.*\\', ''), '@', 1)))
  FROM semantic_audit
 WHERE at >= now() - interval '30 days' AND lower(actor) NOT IN ('sistem', 'eposta')
 GROUP BY kind;

-- R5 Ekran ziyareti — usage-map totals["<menü öğesi>"] (Türkiye günüyle son 30 gün)
SELECT route_prefix, COUNT(DISTINCT username)
  FROM semantic_hr_page_visits
 WHERE tenant_id = :t AND day >= (now() AT TIME ZONE 'Europe/Istanbul')::date - 29
 GROUP BY route_prefix;

-- R6 Dolmuş / dolacak zorunlu eğitim — /expiring (durum «doldu» + «dolacak»), gün = HR_LEARNING_ALERT_DAYS
-- En son doğrulanmış sertifika; süresiz (expires_on boş) belge varsa kişi geçerli sayılır. Zorunlu eğitimin birim listesi
-- boşsa bütün etkin çalışanlar.
WITH k AS (SELECT id, required_units_json FROM semantic_hr_courses WHERE tenant_id = :t AND kind = 'zorunlu' AND active),
     e AS (SELECT id, unit_id FROM semantic_hr_employees WHERE tenant_id = :t AND status = 'aktif'),
     pairs AS (SELECT e.id AS employee_id, k.id AS course_id FROM e JOIN k
                 ON k.required_units_json IS NULL OR k.required_units_json::jsonb ? e.unit_id),
     last AS (SELECT c.employee_id, c.course_id,
                     bool_or(c.expires_on IS NULL) AS suresiz, max(c.expires_on) AS son
                FROM semantic_hr_certificates c
               WHERE c.tenant_id = :t AND c.verified_at IS NOT NULL
               GROUP BY c.employee_id, c.course_id)
SELECT
  SUM(CASE WHEN l.employee_id IS NULL THEN 1 ELSE 0 END) AS hic_yok,
  SUM(CASE WHEN NOT l.suresiz AND l.son < (now() AT TIME ZONE 'Europe/Istanbul')::date THEN 1 ELSE 0 END) AS doldu,
  SUM(CASE WHEN NOT l.suresiz AND l.son >= (now() AT TIME ZONE 'Europe/Istanbul')::date
            AND l.son < (now() AT TIME ZONE 'Europe/Istanbul')::date + :gun THEN 1 ELSE 0 END) AS dolacak
  FROM pairs p LEFT JOIN last l ON l.employee_id = p.employee_id AND l.course_id = p.course_id;

-- R7 Tamamlanma oranı — dashboard.matrix (birim × eğitim): iptal edilmemiş oturumlardaki onaylı katılımlar
SELECT COALESCE(e.unit_id, '-') AS unit_id, s.course_id, COUNT(*) AS katilim,
       COUNT(*) FILTER (WHERE n.completed_at IS NOT NULL) AS tamamlanan
  FROM semantic_hr_enrollments n
  JOIN semantic_hr_sessions s ON s.id = n.session_id
  LEFT JOIN semantic_hr_employees e ON e.id = n.employee_id
 WHERE n.tenant_id = :t AND n.approval = 'onaylandi' AND s.state <> 'iptal'
 GROUP BY 1, 2;

-- R8 Anonim geri bildirim — yanıt tablosunda kişi kolonu yok
SELECT column_name FROM information_schema.columns WHERE table_name = 'semantic_hr_learning_feedback' ORDER BY ordinal_position;
