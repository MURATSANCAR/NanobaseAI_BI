-- Kitabın baskı sayısı ve son baskı adedi (Baskı Öneri raporunun okuduğu CRM görünümleri).
-- Tek baskısı olan kitapta son baskı = ilk baskı: geçmiş ilk baskı kararları ve matbaa adet basamakları buradan.
SELECT p.StokKodu            AS stok_kodu,
       p.[Baskı Sayısı]      AS baski_sayisi,
       d.Baskı_Adet          AS son_baski_adet,
       d.SonBaskıTarihi      AS son_baski_tarihi
FROM Timas_MSCRM.dbo.powerbikitap AS p
LEFT JOIN Timas_MSCRM.dbo.powerbikitapdetay AS d ON d.Stok_Kodu = p.StokKodu
