-- Tablo: CRM_YeniKitapDetay
-- Sunucu: 192.168.0.28  Veritabanı: Timas_MSCRM
-- Kaynak: 2025_Yeni_Baskı Öneri Raporu (5).pbit (Power Query'den çözüldü)

select * from powerbikitap as a left join powerbikitapdetay as b on a.StokKodu=b.Stok_Kodu
