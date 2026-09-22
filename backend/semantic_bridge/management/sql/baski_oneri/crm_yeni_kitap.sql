-- İlk yayın tarihi içinde bulunulan aydan 12 ay öncesine kadar olan kitaplar.
SELECT k.new_stokkodu AS stok_kodu, CAST(k.new_ilkyayintarihi AS DATE) AS ilk_yayin_tarihi
FROM Timas_MSCRM.dbo.new_kitap AS k
WHERE k.new_ilkyayintarihi >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - 12, 0)
  AND k.new_stokkodu IS NOT NULL
