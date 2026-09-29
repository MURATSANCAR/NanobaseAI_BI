-- Aşama 0: CRM'de platform adlı firma kartları, Logo bağı ve bu firmaların sipariş tipi × yıl sayısı (pasif kayıt
-- bağlantı süzgecinde düşer). {kosul}: a.Name üzerinde Yönetim ayarındaki adlar. Tutar CRM'den okunmaz.
SELECT a.Name AS ad, a.new_logicalref AS logicalref, o.new_siparistipi AS tip, YEAR(o.new_siparistarihi) AS yil,
  COUNT(o.new_siparisId) AS sayi
FROM {p}AccountBase AS a
LEFT JOIN {p}new_siparisBase AS o ON o.new_firmaid = a.AccountId AND o.new_siparistarihi >= '{bas}'
WHERE ({kosul})
GROUP BY a.Name, a.new_logicalref, o.new_siparistipi, YEAR(o.new_siparistarihi)
