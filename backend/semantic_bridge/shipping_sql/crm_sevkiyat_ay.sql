-- M44 Kargo: bir ayın Logo'ya aktarılmış CRM sevkiyatları (kabul 6: Logo sevk ile eşleşme oranı). Ay sevk tarihinden
-- (İstanbul günü; CRM UTC saklar, sınırlar UTC'ye çevrilmiş verilir).
SELECT v.new_sevkiyatId AS id, v.new_faturanumarasi AS fatura_no, v.new_sevktarihi AS tarih
FROM {p}new_sevkiyatBase v
WHERE v.statecode = 0 AND v.new_logoyaaktarildi = 1 AND v.new_sevktarihi >= '{bas_utc}' AND v.new_sevktarihi < '{bit_utc}'
