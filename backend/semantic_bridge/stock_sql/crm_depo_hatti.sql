-- Sipariş hazırlık hattı: depo aşamasındaki etkin siparişler (Depoda bekliyor → Pusula alındı / toplanıyor →
-- Kutulanıyor → Kutulandı) ve penceredeki sevkler (aşama sürelerinin ölçümü). Kişisel alan okunmaz: toplayıcının
-- yalnız adı (SystemUser.FullName); depo şifresi ve depo kullanıcı adı kolonları hiçbir sorguda seçilmez.
SELECT CAST(s.new_siparisId AS nvarchar(40)) AS id, s.new_name AS siparis_no, CAST(s.statuscode AS int) AS durum,
  CAST(s.new_siparistipi AS int) AS tip, CAST(s.new_siparisoncelikdurumu AS int) AS oncelik,
  s.new_siparistarihi AS siparis_tarihi, s.new_DepodaBekliyorDurumu AS depoda, s.new_pusulaalinditarih AS pusula,
  s.new_sipariskutulanditarihi AS kutulandi, s.new_sevktarihi AS sevk, d.new_name AS depo, u.FullName AS toplayan,
  s.new_kutuadedi AS koli
FROM {crm}new_siparisBase AS s
LEFT JOIN {crm}new_depoBase AS d ON d.new_depoId = s.new_depoid
LEFT JOIN {crm}SystemUserBase AS u ON u.SystemUserId = s.new_pusulayitoplayanid
WHERE (s.statecode = 0 AND s.statuscode IN (100000011, 100000012, 100000013, 100000014))
   OR (s.new_sevktarihi >= '{bas}' AND s.new_DepodaBekliyorDurumu IS NOT NULL)
