-- CRM sipariş tipi etiketleri (new_siparistipi seçim listesi).
SELECT sm.AttributeValue AS kod, sm.Value AS ad
FROM {p}StringMap AS sm
WHERE sm.AttributeName = 'new_siparistipi'
