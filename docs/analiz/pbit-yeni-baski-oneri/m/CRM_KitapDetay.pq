let
    Kaynak = Sql.Database("192.168.0.28", "Timas_MSCRM", [Query="SELECT *
FROM powerbikitap AS a
LEFT JOIN powerbikitapdetay AS b 
    ON a.StokKodu = b.Stok_Kodu
WHERE a.BaskıTarihi < DATEFROMPARTS(
    YEAR(GETDATE()) - 1,
    MONTH(GETDATE()),
    1
)"])
in
    Kaynak
