-- Son 30 günde CRM'e girilen baskı önerileri, stok kodu başına toplam adet.
SELECT k.new_StokKodu AS stok_kodu, SUM(b.new_OnerilenBaskiAdeti) AS oneri_adet
FROM Timas_MSCRM.dbo.new_baskioneri AS b
LEFT JOIN Timas_MSCRM.dbo.new_kitap AS k ON k.new_kitapId = b.new_BaskionerileriId
WHERE b.CreatedOn >= DATEADD(DAY, -30, GETDATE())
GROUP BY k.new_StokKodu
