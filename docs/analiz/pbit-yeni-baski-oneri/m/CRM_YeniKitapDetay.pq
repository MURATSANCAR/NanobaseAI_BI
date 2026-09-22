let
    Kaynak = Sql.Database("192.168.0.28", "Timas_MSCRM", [Query="select * from powerbikitap as a left join powerbikitapdetay as b on a.StokKodu=b.Stok_Kodu"])
in
    Kaynak
