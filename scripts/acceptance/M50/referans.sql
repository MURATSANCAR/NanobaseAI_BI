-- M50 Zeki AI kalitesi — bağımsız referans sorguları (köprü kodu kullanılmadan; test sunucusunda, meta veritabanı
-- bi_meta, salt okunur). kabul.py aynı sorguları :tenant, :ds, :since yerine değer koyarak çalıştırır ve ekrana giden
-- uç cevabıyla karşılaştırır. Pencere = karne penceresi (varsayılan 30 gün).

-- R1 · Karne «Soru-cevap»: cevap türü dağılımı (tanıtım cevabı ölçüme girmez).
SELECT answer_type, count(*) AS n
FROM sl_query_log
WHERE tenant_id = :tenant AND datasource_id = :ds AND created_at >= :since
  AND coalesce(answer_type, '') <> 'MODULE_INTRO'
GROUP BY answer_type;

-- R2 · Karne «Soru-cevap»: cevaplanan (SQL'li, çalıştı, hata yok) ve ret (netleştirme, yetki, bağlantı hariç).
SELECT
  count(*) FILTER (WHERE answer_type = 'TEXT_TO_SQL' AND executed AND error IS NULL) AS cevaplanan,
  count(*) FILTER (WHERE answer_type IN ('INCOMPLETE_ANSWER','DATA_UNAVAILABLE','NON_SQL_QUERY','SQL_INVALID')) AS ret,
  count(*) AS toplam
FROM sl_query_log
WHERE tenant_id = :tenant AND datasource_id = :ds AND created_at >= :since
  AND coalesce(answer_type, '') <> 'MODULE_INTRO';

-- R3 · Karne: kullanıcı hükümleri (pencere içinde verilen).
SELECT verdict, count(*) AS n FROM semantic_mq_feedback
WHERE tenant_id = :tenant AND at >= :since GROUP BY verdict;

-- R4 · Karne «SEO önerileri»: pencerede karar verilen öneriler ve değiştirmeden onay (karar kaydındaki «duzenlenen»).
SELECT status, count(*) AS n FROM semantic_seo_proposals
WHERE tenant_id = :tenant AND decided_at >= :since GROUP BY status;
SELECT count(*) FILTER (WHERE detail::jsonb ? 'duzenlenen') AS bilinen,
       count(*) FILTER (WHERE detail::jsonb ? 'duzenlenen' AND jsonb_array_length(detail::jsonb -> 'duzenlenen') = 0) AS degistirmeden
FROM semantic_audit WHERE kind = 'seo_product' AND action = 'approve' AND at >= :since;

-- R5 · Karne «Çeviri taslağı»: M4 kalite puanı (1 − ceza ÷ incelenen kelime) × 100; küçük 1, büyük 5, kritik 25.
-- İncelenen = pencerede onaylanan segmentler.
WITH seg AS (
  SELECT s.id, s.words FROM semantic_translation_segments s
  JOIN semantic_translation_jobs j ON j.id = s.job_id
  WHERE j.tenant_id = :tenant AND s.status = 'onaylandi' AND s.approved_at >= :since)
SELECT (SELECT coalesce(sum(words), 0) FROM seg) AS incelenen_kelime,
       (SELECT coalesce(sum(CASE e.severity WHEN 'kucuk' THEN 1 WHEN 'buyuk' THEN 5 WHEN 'kritik' THEN 25 ELSE 0 END), 0)
          FROM semantic_translation_errors e WHERE e.segment_id IN (SELECT id FROM seg)) AS ceza;
-- Taslağı olan onaylı segmentler ve taslağı değiştirilen (boşluk sadeleştirilerek karşılaştırılır; kabul.py Python'da).
SELECT s.draft, s.target FROM semantic_translation_segments s JOIN semantic_translation_jobs j ON j.id = s.job_id
WHERE j.tenant_id = :tenant AND s.status = 'onaylandi' AND s.approved_at >= :since AND coalesce(s.draft, '') <> '';

-- R6 · Karne «Redaksiyon önerileri»: kabul / red ve değiştirilerek kabul.
SELECT g.status, count(*) AS n,
       count(*) FILTER (WHERE g.status = 'kabul' AND g.applied_text IS NOT NULL AND g.applied_text <> g.suggestion) AS degistirilerek
FROM semantic_editorial_suggestions g JOIN semantic_editorial_works w ON w.id = g.work_id
WHERE w.tenant_id = :tenant AND g.decided_at >= :since GROUP BY g.status;

-- R7 · Koşu ayrıntısı: vaka durumları (API'deki tally ile aynı olmalı).
SELECT status, count(*) AS n FROM semantic_mq_cases WHERE run_id = :run GROUP BY status;

-- R8 · Eş anlamlı kararları (karar kuyruğu sonraki sürümde; bugünkü sayılar bilgi olarak yazılır).
SELECT status, count(*) AS n FROM sl_vocabulary WHERE tenant_id = :tenant AND datasource_id = :ds GROUP BY status;

-- R9 · Geri bildirim yazımı: deneme cevabına «Yanlış + not» sonrası.
SELECT validated FROM sl_query_log WHERE id = :qid;
SELECT verdict, comment, triage_state FROM semantic_mq_feedback WHERE query_id = :qid;
