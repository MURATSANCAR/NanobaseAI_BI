-- Logo'ya aktarılmamış hareketlerin kitap başına net miktarı (işlem tipi giriş + / çıkış −). Logo–CRM farkının kök
-- nedeni: CRM'de olup Logo'ya geçmemiş hareket, CRM raf stoğu − Logo bakiyesi farkını açıklar.
SELECT p.ProductNumber AS stok_kodu,
  SUM(CASE WHEN h.new_islemtipi = 1 THEN s.new_miktar WHEN h.new_islemtipi = 2 THEN -s.new_miktar ELSE 0 END) AS net,
  COUNT(DISTINCT h.new_malzemehareketiId) AS fis
FROM {crm}new_malzemehareketiBase AS h
JOIN {crm}new_malzemehareketsatiriBase AS s ON s.new_malzemehareketiid = h.new_malzemehareketiId AND s.statecode = 0
JOIN {crm}ProductBase AS p ON p.ProductId = s.new_urunid
WHERE h.new_logoyaaktarildi = 0 AND h.statecode = 0
GROUP BY p.ProductNumber
