-- M52 Üretim kartı ve plan takvimi seçenek listelerinin Türkçe adları (ciltleme şekli, baskı tipi, değişiklik sebebi).
SELECT s.AttributeName AS attr, s.AttributeValue AS code, s.Value AS label
FROM {crm}StringMapBase s
WHERE s.ObjectTypeCode IN (SELECT e.ObjectTypeCode FROM {crm}EntityView e WHERE e.Name IN ('new_uretim', 'new_uretimplanlamatakvimi'))
  AND s.AttributeName IN ('new_ciltlemesekli', 'new_baskitipi', 'new_degisikliksebebi') AND s.LangId = 1055
