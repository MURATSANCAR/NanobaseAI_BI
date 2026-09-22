-- Tablo: CRM_KitapDetay
-- Sunucu: 192.168.0.28  Veritabanı: Timas_MSCRM
-- Kaynak: 2025_Yeni_Baskı Öneri Raporu (5).pbit (Power Query'den çözüldü)

SELECT *
FROM powerbikitap AS a
LEFT JOIN powerbikitapdetay AS b 
    ON a.StokKodu = b.Stok_Kodu
WHERE a.BaskıTarihi < DATEFROMPARTS(
    YEAR(GETDATE()) - 1,
    MONTH(GETDATE()),
    1
)
