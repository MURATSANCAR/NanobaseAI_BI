-- CRM depo kartları (45 tanım, 2026-09-15 profili): ad, kod, numara, Logo ambar maliyet grubu, etkin raf sayısı.
SELECT CAST(d.new_depoId AS nvarchar(40)) AS depo_id, d.new_name AS depo, d.new_depokodu AS depo_kodu,
  d.new_deponumarasi AS depo_no, d.new_ambarmaliyetgrubu AS maliyet_grubu, CAST(d.statecode AS int) AS durum,
  (SELECT COUNT(*) FROM {crm}new_rafBase AS r WHERE r.new_depoid = d.new_depoId AND r.statecode = 0) AS raf_sayisi
FROM {crm}new_depoBase AS d
