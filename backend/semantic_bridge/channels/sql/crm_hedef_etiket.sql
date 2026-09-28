-- new_yil ve new_bolge seçim listelerinin etiketleri: yalnız satış hedefleri tablosunda kullanılan kodlar.
-- Aynı alan adı başka varlıkta da olabilir; kod çakışırsa yıl etiketi dört haneli yıl içeren alınır (sources.py).
SELECT sm.AttributeName AS alan, sm.AttributeValue AS kod, sm.Value AS ad
FROM {schema}.StringMap AS sm
WHERE (sm.AttributeName = 'new_yil' AND sm.AttributeValue IN (SELECT DISTINCT new_yil FROM {schema}.new_satishedefleriBase))
   OR (sm.AttributeName = 'new_bolge' AND sm.AttributeValue IN (SELECT DISTINCT new_bolge FROM {schema}.new_satishedefleriBase))
