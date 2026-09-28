-- M58 Çalışan deneyimi — bağımsız referans sorguları (bi_meta Postgres). Test anketi yapay «KABUL TESTİ M58» birimine açılır;
-- gerçek çalışanın cevabı yazılmaz. answers_json metin kolonudur (json'a çevrilir).

-- K1 Hedef kitle (davet) sayısı: hedef birim ve alt birimlerindeki, hesabı olan aktif çalışanlar
WITH RECURSIVE agac AS (
  SELECT id FROM semantic_hr_units WHERE id IN (:hedef_birimler)
  UNION SELECT u.id FROM semantic_hr_units u JOIN agac ON u.parent_id = agac.id
) SELECT COUNT(*) FROM semantic_hr_employees
  WHERE tenant_id = :t AND status = 'aktif' AND username IS NOT NULL AND unit_id IN (SELECT id FROM agac);

-- K2 Yanıt oranı (anket açıkken; kapanınca davetler silinir, sayılar ankette kalır)
SELECT COUNT(*) FILTER (WHERE responded) * 1.0 / COUNT(*) FROM semantic_hr_survey_invites WHERE survey_id = :s;
SELECT COUNT(*) FROM semantic_hr_survey_responses WHERE survey_id = :s;   -- = cevaplayan davetli + kullanılan basılı kod

-- K3 eNPS
SELECT 100.0 * (COUNT(*) FILTER (WHERE (answers_json::json->>'enps')::int >= 9)
              - COUNT(*) FILTER (WHERE (answers_json::json->>'enps')::int <= 6))
       / COUNT(*) FILTER (WHERE answers_json::json->>'enps' IS NOT NULL)
FROM semantic_hr_survey_responses WHERE survey_id = :s;

-- K4 Madde ortalaması (her Likert maddesi)
SELECT AVG((answers_json::json->>:madde)::numeric) FROM semantic_hr_survey_responses WHERE survey_id = :s;

-- K5 Anonimlik (şema): cevap ve yorum tablolarında kişi/jeton/saat kolonu yok; gün tipi date
SELECT table_name, column_name, data_type FROM information_schema.columns
WHERE table_name IN ('semantic_hr_survey_responses', 'semantic_hr_survey_comments');

-- K6 Anonimlik (eşleme): davet ile cevap arasında ortak kolon (kimlik, zaman, sıra) yok
SELECT column_name FROM information_schema.columns WHERE table_name = 'semantic_hr_survey_invites'
INTERSECT
SELECT column_name FROM information_schema.columns WHERE table_name = 'semantic_hr_survey_responses';
-- beklenen: yalnız survey_id, tenant_id

-- K7 Kapanış sonrası katılım izi yok
SELECT COUNT(*) FROM semantic_hr_survey_invites WHERE survey_id = :s;     -- 0
SELECT COUNT(*) FROM semantic_hr_survey_paper_codes WHERE survey_id = :s; -- 0
