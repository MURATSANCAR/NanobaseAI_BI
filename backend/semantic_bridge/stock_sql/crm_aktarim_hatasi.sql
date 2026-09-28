-- Logo'ya aktarılmamış etkin CRM malzeme hareketleri (yön CRM → Logo). «Hata» = Logo mesajı dolu
-- (new_logomesaji IS NOT NULL); mesajsız olan henüz aktarılmamış (bekliyor). Satır sayısı ve miktar fişin etkin satırlarından.
SELECT CAST(h.new_malzemehareketiId AS nvarchar(40)) AS id, h.new_name AS fis_no, h.new_belgeno AS belge_no,
  h.new_fistarihi AS fis_tarihi, h.CreatedOn AS olusturma, CAST(h.new_islemturu AS int) AS islem_turu,
  CAST(h.new_islemtipi AS int) AS islem_tipi, CAST(h.statuscode AS int) AS durum, d.new_name AS depo,
  CASE WHEN h.new_logomesaji IS NOT NULL THEN 1 ELSE 0 END AS hata,
  CAST(h.new_logomesaji AS nvarchar(max)) AS mesaj,
  s.satir, s.miktar
FROM {crm}new_malzemehareketiBase AS h
LEFT JOIN {crm}new_depoBase AS d ON d.new_depoId = h.new_depoid
LEFT JOIN (
  SELECT x.new_malzemehareketiid AS hid, COUNT(*) AS satir, SUM(x.new_miktar) AS miktar
  FROM {crm}new_malzemehareketsatiriBase AS x
  WHERE x.statecode = 0 AND x.new_malzemehareketiid IN (
    SELECT new_malzemehareketiId FROM {crm}new_malzemehareketiBase WHERE new_logoyaaktarildi = 0 AND statecode = 0)
  GROUP BY x.new_malzemehareketiid
) AS s ON s.hid = h.new_malzemehareketiId
WHERE h.new_logoyaaktarildi = 0 AND h.statecode = 0
