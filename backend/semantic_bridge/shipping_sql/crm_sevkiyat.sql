-- M44 Kargo: siparişin CRM sevkiyatları (Logo'ya aktarıldı mı, fatura numarası, müşteriye sevk e-postası gitti mi).
SELECT v.new_sevkiyatId AS id, v.new_name AS no, v.new_siparisid AS siparis_id, v.new_sevktarihi AS tarih,
  CAST(v.new_sevkiyat_islemturu AS int) AS tur, v.new_faturanumarasi AS fatura_no, CAST(v.new_logoyaaktarildi AS int) AS logoda,
  CAST(v.new_sevkiyatmailigonderildi AS int) AS eposta
FROM {p}new_sevkiyatBase v
WHERE v.statecode = 0 AND v.new_siparisid IN ({siparisler})
ORDER BY v.new_sevktarihi
