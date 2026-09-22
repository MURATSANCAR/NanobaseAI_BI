let
    Source = Sql.Database("192.168.0.28", "Timas_MSCRM", [Query="SELECT #(lf)      #(lf)      [STOK_KODU]#(lf)      ,SUM(CONVERT (int, [Bekl_Adet],0)) SipAdet#(lf)#(lf)  FROM [Timas_MSCRM].[dbo].[pbi_bekleyen_sip] where SIP_TARIHI <= GETDATE() AND SIP_TARIHI >= DATEADD(week, -2, GETDATE())#(lf)  Group  BY [STOK_KODU]"])
in
    Source
