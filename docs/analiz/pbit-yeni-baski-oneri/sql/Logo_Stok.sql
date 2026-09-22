-- Tablo: Logo_Stok
-- Sunucu: 192.168.0.25  Veritabanı: LOGO_DB
-- Kaynak: 2025_Yeni_Baskı Öneri Raporu (5).pbit (Power Query'den çözüldü)

SELECT [STOK KODU]
      ,[STOK ADI]
      ,SUM([MİKTAR]) as Stok
  FROM [LOGO_DB].[dbo].[EOS_DEPO_STOK_KONTROL_211]
  Where [STOK KODU] not like '157%'
  Group By
       [STOK KODU]
      ,[STOK ADI]
