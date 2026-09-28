-- CRM raf stoğu: seri/lot hareket satırının kalan miktarı (new_kalanmiktar), ürün × raf × depo. Etkin satırlar.
-- Ürün bağı lotun malzeme hareket satırından (new_urunid → Product.ProductNumber = Logo stok kodu).
-- «Kalan miktar»ın güncel raf stoğu olup olmadığı test sunucusunda ölçülecek (analiz Soru 1); fark ekranı bu toplamı okur.
SELECT p.ProductNumber AS stok_kodu,
  CAST(r.new_rafId AS nvarchar(40)) AS raf_id, r.new_name AS raf, CAST(r.new_raftipi AS int) AS raf_tipi,
  CAST(r.new_satisaacik AS int) AS satisa_acik, r.new_rafyerlesimonceligi AS yerlesim,
  CAST(d.new_depoId AS nvarchar(40)) AS depo_id, d.new_name AS depo, d.new_deponumarasi AS depo_no,
  SUM(s.new_kalanmiktar) AS kalan
FROM {crm}new_serilothareketsatiriBase AS s
JOIN {crm}new_malzemehareketsatiriBase AS m ON m.new_malzemehareketsatiriId = s.new_malzemehareketsatiriid
JOIN {crm}ProductBase AS p ON p.ProductId = m.new_urunid
LEFT JOIN {crm}new_rafBase AS r ON r.new_rafId = s.new_rafid
LEFT JOIN {crm}new_depoBase AS d ON d.new_depoId = r.new_depoid
WHERE s.statecode = 0 AND s.new_kalanmiktar <> 0
GROUP BY p.ProductNumber, r.new_rafId, r.new_name, r.new_raftipi, r.new_satisaacik, r.new_rafyerlesimonceligi,
  d.new_depoId, d.new_name, d.new_deponumarasi
