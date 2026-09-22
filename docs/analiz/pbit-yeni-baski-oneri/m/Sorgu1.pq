let
    Kaynak = Sql.Database("192.168.0.28", "Timas_MSCRM", [Query="Select K.new_StokKodu,K.new_name,B.new_OnerilenBaskiAdeti,b.CreatedOn as OneriTarih from new_baskioneri as b#(lf)Left Join new_kitap as k on K.new_kitapId = b.new_BaskionerileriId  WHERE 
    B.CreatedOn >= DATEADD(DAY, -30, GETDATE())"])
in
    Kaynak
