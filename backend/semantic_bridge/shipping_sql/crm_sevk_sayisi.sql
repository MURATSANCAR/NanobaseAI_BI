-- M44 Kargo: sevk edilen sipariş sayısı (günlük hat başlığı; kabul 1). {durumlar} = sevk edilmiş sayılan durumlar
-- (ayar SHIPPING_SHIPPED_STATUSES), pencere sevk tarihinden. Bugün = İstanbul günü; CRM tarihi UTC saklar, sınır UTC verilir.
SELECT COUNT(*) AS adet,
  SUM(CASE WHEN s.new_sevktarihi >= '{bugun_utc}' THEN 1 ELSE 0 END) AS bugun
FROM {p}new_siparisBase s
WHERE s.statecode = 0 AND CAST(s.statuscode AS int) IN ({durumlar}) AND s.new_sevktarihi >= '{bas}'
