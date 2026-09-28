-- M44 Kargo: siparişin takip bilgisi kayıtları (irsaliye/fatura no ve takip numarası), sipariş kimliğiyle.
SELECT k.new_kargotakipbilgisiId AS id, k.new_name AS belge_no, k.new_kargotakipnumarasi AS takip_no,
  k.new_siparisid AS siparis_id, k.CreatedOn AS olusturma
FROM {p}new_kargotakipbilgisiBase k
WHERE k.statecode = 0 AND k.new_siparisid IN ({siparisler})
