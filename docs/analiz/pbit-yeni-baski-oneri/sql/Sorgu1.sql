-- Tablo: Sorgu1
-- Sunucu: 192.168.0.28  Veritabanı: Timas_MSCRM
-- Kaynak: 2025_Yeni_Baskı Öneri Raporu (5).pbit (Power Query'den çözüldü)

Select K.new_StokKodu,K.new_name,B.new_OnerilenBaskiAdeti,b.CreatedOn as OneriTarih from new_baskioneri as b
Left Join new_kitap as k on K.new_kitapId = b.new_BaskionerileriId  WHERE 
    B.CreatedOn >= DATEADD(DAY, -30, GETDATE())
