-- M52 Kağıt cinsleri ve ebatları (CRM, yalnız okuma): üretim kartındaki kağıt cinsi / ebat kimliklerinin adı.
SELECT 'cins' AS tur, k.new_kagitcinsiId AS id, k.new_name AS ad, k.new_gramaj AS gramaj, k.new_Bulk AS bulk,
  k.new_kagitsiralama AS sira
FROM {crm}new_kagitcinsiBase k
UNION ALL
SELECT 'ebat' AS tur, e.new_kagitebadiId AS id, e.new_name AS ad, NULL AS gramaj, NULL AS bulk, NULL AS sira
FROM {crm}new_kagitebadiBase e
