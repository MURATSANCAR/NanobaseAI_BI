-- M41 CRM Amazon Konsinye siparişleri (kabul 4): sipariş tipi {tip} (varsayılan 14 «Amazon Konsinye»), yıl başına sayı.
-- Tutar CRM'den okunmaz (kayıt sistemi Logo); yalnız sipariş sayısı.
SELECT YEAR(o.new_siparistarihi) AS yil, COUNT(*) AS sayi
FROM {schema}new_siparisBase AS o
WHERE o.statecode = 0 AND o.new_siparistipi = {tip} AND o.new_siparistarihi >= '{bas}'
GROUP BY YEAR(o.new_siparistarihi)
