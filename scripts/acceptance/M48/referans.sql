-- M48 Sistem durumu — bağımsız referans sorguları (test sunucusunda; Logo/CRM doğrudan bağlantıyla, meta DB psql ile).
-- kabul.py bunları kendi parametreleriyle koşturur; elle koşturmak için yer tutuculu hâlleri burada.
-- Firma: 411 = 2026 (güncel kopya, .155 donmuş: son fatura 2026-08-17), 211 = 2021–2025.

-- R1. Logo veri sonu (analiz §14 kabul 1). Portal: son «logo» denetiminin data_end'i (gün), Durum sekmesi Logo kartı.
--     Bugünden ileri tarihli hatalı fatura veriyi taze göstermesin diye bugünle sınırlı (portal da aynı sınırı koyar).
SELECT MAX(DATE_) AS son FROM LG_411_01_INVOICE WHERE CANCELLED = 0 AND DATE_ <= CAST(GETDATE() AS date);

-- R1b. Aynı sayı sınırsız (analizdeki biçim) — ileri tarihli kayıt var mı diye bakmak için; R1'den büyükse ileri tarihli kayıt vardır.
SELECT MAX(DATE_) AS son_sinirsiz FROM LG_411_01_INVOICE WHERE CANCELLED = 0;

-- R2. CRM veri sonu (kabul 2). Portal: son «crm» denetiminin data_end'i (UTC, dakika hassasiyeti; arada değişiklik olabilir).
SELECT MAX(ModifiedOn) AS son FROM Timas_MSCRM.dbo.new_kitapBase WHERE ModifiedOn <= GETUTCDATE();

-- R3. Hatalı planlı rapor sayısı (kabul 3). Portal: Zamanlanmış işler «Planlı raporlar» satırı = Yönetim özetindeki reportsFailed.
SELECT count(*) FROM semantic_reports WHERE tenant_id = '{tenant}' AND datasource_id = '{ds}' AND last_status = 'failed';

-- R4. Hatalı pano kartı sayısı (kabul 4). Portal: «Pano kartı tazeleme» satırı.
SELECT count(*) FROM semantic_board_cards WHERE tenant_id = '{tenant}' AND datasource_id = '{ds}' AND last_error IS NOT NULL;

-- R5. Model kuyruğu, modül başına ortanca (kabul 5). Portal: Kapasite sekmesi «Zeki AI kapasitesi» tablosu.
SELECT module,
       count(*) AS is_sayisi,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY queue_wait_ms) AS bekleme_p50,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY llm_ms) AS model_p50
FROM sl_llm_job WHERE created_at > now() - interval '7 days' AND status = 'DONE' GROUP BY module ORDER BY 2 DESC;

-- R6. Hatalı uyarı kuralı sayısı. Portal: «Uyarı kuralları» satırı.
SELECT count(*) FROM semantic_alert_rules WHERE tenant_id = '{tenant}' AND datasource_id = '{ds}' AND state = 'error';

-- R7. Sürüm eşliği (kabul 8). Son test ve VM kaydı; code_sha = kurulum anındaki `git rev-parse main`, appledouble_count = 0.
SELECT DISTINCT ON (env) env, at, code_sha, image, appledouble_count FROM semantic_itops_releases ORDER BY env, id DESC;

-- R8. Son 7 günün kopma dakikası (haftalık özetin sayısı). Portal: Olaylar sekmesi «Son 30 gün» kutuları 30 günle.
SELECT ring, count(*) AS kopma,
       sum(extract(epoch FROM (least(coalesce(closed_at, now()), now()) - greatest(opened_at, now() - interval '7 days'))) / 60)::int AS dakika
FROM semantic_itops_incidents
WHERE kind = 'kopma' AND false_alarm = false AND opened_at < now() AND (closed_at IS NULL OR closed_at > now() - interval '7 days')
GROUP BY ring;
