-- Kitap kartında editörün girdiği emsal kitaplar (CRM «Emsal kitap» ilişkisi).
-- İlişkinin birinci tarafı kitabın kendisi, ikinci tarafı emsalidir (ölçüm 2026-09-28: 2021 sonrası kitapların
-- emsallerinin %98'i kitaptan önce yayımlanmış).
SELECT k1.new_stokkodu AS stok_kodu,
       k2.new_stokkodu AS emsal_stok_kodu
FROM Timas_MSCRM.dbo.new_new_kitap_new_emsalkitap3Base AS e
JOIN Timas_MSCRM.dbo.new_kitapBase AS k1 ON k1.new_kitapId = e.new_kitapidOne
JOIN Timas_MSCRM.dbo.new_kitapBase AS k2 ON k2.new_kitapId = e.new_kitapidTwo
WHERE k1.new_stokkodu IS NOT NULL AND k2.new_stokkodu IS NOT NULL AND k1.new_stokkodu <> k2.new_stokkodu
