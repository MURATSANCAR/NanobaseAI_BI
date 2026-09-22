let
    Kaynak = Sql.Database("192.168.0.25", "LOGO_DB", [Query="DECLARE @End_Date_1 DATE = CAST(DATEADD(MONTH, DATEDIFF(MONTH, -1, GETDATE())-1, -1) AS DATE);
DECLARE @Start_Date_1 DATE = CAST(DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE())-6, 0) AS DATE);
DECLARE @End_Date_2 DATE = CAST(DATEADD(MONTH, DATEDIFF(MONTH, -1, GETDATE())-7, -1) AS DATE);
DECLARE @Start_Date_2 DATE = CAST(DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE())-12, 0) AS DATE);

DECLARE @Ceyrek_Start_1 DATE = CAST(DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE())-3, 0) AS DATE);
DECLARE @Ceyrek_End_1 DATE = CAST(DATEADD(MONTH, DATEDIFF(MONTH, -1, GETDATE())-1, -1) AS DATE);
DECLARE @Ceyrek_Start_2 DATE = CAST(DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE())-6, 0) AS DATE);
DECLARE @Ceyrek_End_2 DATE = CAST(DATEADD(MONTH, DATEDIFF(MONTH, -1, GETDATE())-4, -1) AS DATE);
DECLARE @Ceyrek_Start_3 DATE = CAST(DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE())-9, 0) AS DATE);
DECLARE @Ceyrek_End_3 DATE = CAST(DATEADD(MONTH, DATEDIFF(MONTH, -1, GETDATE())-7, -1) AS DATE);
DECLARE @Ceyrek_Start_4 DATE = CAST(DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE())-12, 0) AS DATE);
DECLARE @Ceyrek_End_4 DATE = CAST(DATEADD(MONTH, DATEDIFF(MONTH, -1, GETDATE())-10, -1) AS DATE);


DECLARE @Gun_Sayisi INT = DAY(GETDATE());
PRINT CAST(@Gun_Sayisi AS VARCHAR);

PRINT 'Ilk 6 Ay (' + CAST(@Start_Date_1 AS VARCHAR) + ' Ve ' + CAST(@End_Date_1 AS VARCHAR) + ') Arasinda';
PRINT 'Son 6 Ay (' + CAST(@Start_Date_2 AS VARCHAR) + ' Ve ' + CAST(@End_Date_2 AS VARCHAR) + ') Arasinda';
PRINT '';
PRINT '4. Ceyrek (' + CAST(@Ceyrek_Start_4 AS VARCHAR) + ' Ve ' + CAST(@Ceyrek_End_4 AS VARCHAR) + ') Arasinda';
PRINT '3. Ceyrek (' + CAST(@Ceyrek_Start_3 AS VARCHAR) + ' Ve ' + CAST(@Ceyrek_End_3 AS VARCHAR) + ') Arasinda';
PRINT '2. Ceyrek (' + CAST(@Ceyrek_Start_2 AS VARCHAR) + ' Ve ' + CAST(@Ceyrek_End_2 AS VARCHAR) + ') Arasinda';
PRINT '1. Ceyrek (' + CAST(@Ceyrek_Start_1 AS VARCHAR) + ' Ve ' + CAST(@Ceyrek_End_1 AS VARCHAR) + ') Arasinda';

SELECT 
    [Malzeme/Hizmet Kodu],
    SUM(CASE WHEN [Fatura Tarihi] >= @Start_Date_1 AND [Fatura Tarihi] <= @End_Date_1 THEN Miktar / 6 ELSE 0 END) AS Ilk6AyOrt,
    SUM(CASE WHEN [Fatura Tarihi] >= @Start_Date_1 AND [Fatura Tarihi] <= @End_Date_1 THEN Miktar ELSE 0 END) AS Ilk6Ay,
    SUM(CASE WHEN [Fatura Tarihi] >= @Start_Date_2 AND [Fatura Tarihi] <= @End_Date_2 THEN Miktar / 6 ELSE 0 END) AS Son6AyOrt,
    SUM(CASE WHEN [Fatura Tarihi] >= @Start_Date_2 AND [Fatura Tarihi] <= @End_Date_2 THEN Miktar ELSE 0 END) AS Son6Ay,
    SUM(CASE WHEN [Fatura Tarihi] >= @Ceyrek_Start_1 AND [Fatura Tarihi] <= @Ceyrek_End_1 THEN Miktar ELSE 0 END) AS Ceyrek1,
    SUM(CASE WHEN [Fatura Tarihi] >= @Ceyrek_Start_2 AND [Fatura Tarihi] <= @Ceyrek_End_2 THEN Miktar ELSE 0 END) AS Ceyrek2,
    SUM(CASE WHEN [Fatura Tarihi] >= @Ceyrek_Start_3 AND [Fatura Tarihi] <= @Ceyrek_End_3 THEN Miktar ELSE 0 END) AS Ceyrek3,
    SUM(CASE WHEN [Fatura Tarihi] >= @Ceyrek_Start_4 AND [Fatura Tarihi] <= @Ceyrek_End_4 THEN Miktar ELSE 0 END) AS Ceyrek4,
    SUM(CASE WHEN [Fatura Tarihi] >= @Ceyrek_Start_1 AND [Fatura Tarihi] <= @Ceyrek_End_1 THEN Miktar / 3 ELSE 0 END) AS Ceyrek1Ort,
    SUM(CASE WHEN [Fatura Tarihi] >= @Ceyrek_Start_2 AND [Fatura Tarihi] <= @Ceyrek_End_2 THEN Miktar / 3 ELSE 0 END) AS Ceyrek2Ort,
    SUM(CASE WHEN [Fatura Tarihi] >= @Ceyrek_Start_3 AND [Fatura Tarihi] <= @Ceyrek_End_3 THEN Miktar / 3 ELSE 0 END) AS Ceyrek3Ort,
    SUM(CASE WHEN [Fatura Tarihi] >= @Ceyrek_Start_4 AND [Fatura Tarihi] <= @Ceyrek_End_4 THEN Miktar / 3 ELSE 0 END) AS Ceyrek4Ort,
    SUM(CASE WHEN [Fatura Tarihi] >= @Start_Date_2 AND [Fatura Tarihi] <= @End_Date_1 THEN Miktar ELSE 0 END) AS YillikToplami,
    SUM(CASE WHEN [Fatura Tarihi] >= @Start_Date_2 AND [Fatura Tarihi] <= @End_Date_1 THEN Miktar / 12 ELSE 0 END) AS YillikToplamiOrt,
    SUM(CASE WHEN [Fatura Tarihi] <= CAST(DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - 1, 0) AS DATE) AND [Fatura Tarihi] >= @End_Date_2 THEN Miktar ELSE 0 END) AS BuAyinToplami,
    (
        SUM(CASE WHEN [Fatura Tarihi] >= @Ceyrek_Start_4 AND [Fatura Tarihi] <= @Ceyrek_End_4 THEN Miktar / 3 * 0.2 ELSE 0 END) +
        SUM(CASE WHEN [Fatura Tarihi] >= @Ceyrek_Start_3 AND [Fatura Tarihi] <= @Ceyrek_End_3 THEN Miktar / 3 * 0.05 ELSE 0 END) +
        SUM(CASE WHEN [Fatura Tarihi] >= @Ceyrek_Start_2 AND [Fatura Tarihi] <= @Ceyrek_End_2 THEN Miktar / 3 * 0.1 ELSE 0 END) +
        SUM(CASE WHEN [Fatura Tarihi] >= @Ceyrek_Start_1 AND [Fatura Tarihi] <= @Ceyrek_End_1 THEN Miktar / 3 * 0.5 ELSE 0 END) +
        SUM(CASE WHEN [Fatura Tarihi] >= @Start_Date_1 AND [Fatura Tarihi] <= @End_Date_1 THEN Miktar / 6 * 0.05 ELSE 0 END) +
        SUM(CASE WHEN [Fatura Tarihi] >= @Start_Date_2 AND [Fatura Tarihi] <= @End_Date_2 THEN Miktar / 6 * 0.05 ELSE 0 END) +
        SUM(CASE WHEN [Fatura Tarihi] >= @Start_Date_2 AND [Fatura Tarihi] <= @End_Date_1 THEN Miktar / 12 * 0.05 ELSE 0 END)
    ) AS SatisHizi
FROM 
    V_SatisRaporu_All2
WHERE Yıl >= 2024
GROUP BY 
    [Malzeme/Hizmet Kodu]
ORDER BY 
    [Malzeme/Hizmet Kodu];
"]),
    #"Birleştirilen Sorgular" = Table.NestedJoin(Kaynak, {"Malzeme/Hizmet Kodu"}, CRM_KitapDetay, {"StokKodu"}, "CRM_KitapDetay", JoinKind.LeftOuter),
    #"Genişletilen CRM_KitapDetay" = Table.ExpandTableColumn(#"Birleştirilen Sorgular", "CRM_KitapDetay", {"StokAdedi"}, {"CRM_KitapDetay.StokAdedi"}),
    #"Yeniden Adlandırılan Sütunlar" = Table.RenameColumns(#"Genişletilen CRM_KitapDetay",{{"SatisHizi", "OrtSatisHizi"}})
in
    #"Yeniden Adlandırılan Sütunlar"
