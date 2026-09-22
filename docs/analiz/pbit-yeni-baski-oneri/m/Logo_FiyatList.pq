let
    Kaynak = Sql.Database("192.168.0.25", "LOGO_DB", [Query="WITH MinValues AS (#(lf)    SELECT StokKodu, BirimFiyat, MIN(DateField) AS MinDateField#(lf)    FROM PBI_FiyatList#(lf)    GROUP BY StokKodu, BirimFiyat#(lf)),#(lf)SortedMinValues AS (#(lf)    SELECT *, ROW_NUMBER() OVER(PARTITION BY StokKodu ORDER BY MinDateField DESC) AS RowNum#(lf)    FROM MinValues#(lf))#(lf)SELECT *#(lf)FROM SortedMinValues#(lf)WHERE RowNum = 1#(lf)ORDER BY StokKodu ASC, BirimFiyat DESC;"])
in
    Kaynak
