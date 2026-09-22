-- Tablo: CRM_BekleyenSiparis
-- Sunucu: 192.168.0.28  Veritabanı: Timas_MSCRM
-- Kaynak: 2025_Yeni_Baskı Öneri Raporu (5).pbit (Power Query'den çözüldü)

SELECT 
      
      [STOK_KODU]
      ,SUM(CONVERT (int, [Bekl_Adet],0)) SipAdet

  FROM [Timas_MSCRM].[dbo].[pbi_bekleyen_sip] where SIP_TARIHI <= GETDATE() AND SIP_TARIHI >= DATEADD(week, -2, GETDATE())
  Group  BY [STOK_KODU]
