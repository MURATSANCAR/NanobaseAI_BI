-- İlk yayın tarihi içinde bulunulan aydan 12 ay öncesine kadar olan kitaplar.
-- CRM tarihi UTC saklar: İstanbul'da 1 Kasım 00:00 olan yayın `2025-10-31 21:00` görünür. Power BI tekrar
-- sipariş (RPT) sınırını bu saatli değerle kurar (DATEADD(MONTH, 1, ilk yayın)); aynı sınır için saatli
-- değer de okunur. Ekrandaki ilk yayın ve dağılım ayı Power BI'daki gibi tarihten (UTC gün) alınır.
SELECT k.new_stokkodu AS stok_kodu,
       CAST(k.new_ilkyayintarihi AS DATE) AS ilk_yayin_tarihi,
       k.new_ilkyayintarihi AS ilk_yayin_zamani
FROM Timas_MSCRM.dbo.new_kitap AS k
WHERE k.new_ilkyayintarihi >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - 12, 0)
  AND k.new_stokkodu IS NOT NULL
