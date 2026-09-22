let
    Kaynak = Sql.Database("192.168.0.25", "LOGO_DB", [Query="SELECT [STOK KODU]#(lf)      ,[STOK ADI]#(lf)      ,SUM([MİKTAR]) as Stok#(lf)  FROM [LOGO_DB].[dbo].[EOS_DEPO_STOK_KONTROL_211]#(lf)  Where [STOK KODU] not like '157%'#(lf)  Group By#(lf)       [STOK KODU]#(lf)      ,[STOK ADI]"])
in
    Kaynak
