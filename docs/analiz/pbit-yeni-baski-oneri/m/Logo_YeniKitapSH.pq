let
    Kaynak = Sql.Database("192.168.0.25", "LOGO_DB", [Query="DECLARE @Start_Date_1 DATE = DATEADD(MONTH, -11, DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1));
DECLARE @End_Date_1   DATE = EOMONTH(GETDATE());
PRINT 'Son yil (' + CAST(@Start_Date_1 AS VARCHAR) + ' Ve ' + CAST(@End_Date_1 AS VARCHAR)  + ') Arasinda'; 


WITH FirstQuery AS (
    SELECT CAST(k.new_ilkyayintarihi AS DATE) AS IlkYayinTarihi,
           K.new_stokkodu,
           DATEDIFF(MONTH, k.new_ilkyayintarihi, GETDATE()) AS SatisSuresi,
           SUM(CASE WHEN [Fatura Tarihi] >= @Start_Date_1 AND [Fatura Tarihi] <= @End_Date_1 THEN S.Miktar ELSE 0 END) AS SonBirYilSatis,
           (SUM(CASE WHEN [Fatura Tarihi] >= @Start_Date_1 AND [Fatura Tarihi] <= @End_Date_1 THEN S.Miktar ELSE 0 END)/NULLIF(DATEDIFF(MONTH, k.new_ilkyayintarihi, GETDATE()), 0)) AS SonBirYilSatisOrtalamasi,
           SUM(CASE WHEN (S.Yıl = YEAR(k.new_ilkyayintarihi) AND S.Ay = MONTH(k.new_ilkyayintarihi)) THEN S.Miktar ELSE 0 END) AS DagilimSatıs,
           SUM(CASE WHEN [Fatura Tarihi] >= DATEADD(MONTH, 1, k.new_ilkyayintarihi) THEN S.Miktar ELSE 0 END) AS RPTSatis,
           (SUM(CASE WHEN [Fatura Tarihi] >= DATEADD(MONTH, 1, k.new_ilkyayintarihi) THEN S.Miktar ELSE 0 END)/NULLIF(DATEDIFF(MONTH, k.new_ilkyayintarihi, GETDATE()),0)) AS RPTHizi,
           SUM(CASE WHEN S.Ay = MONTH(GETDATE()) AND S.Yıl = YEAR(GETDATE()) THEN S.Miktar ELSE 0 END) AS BuAyinSatisi,
		   ((SUM(CASE WHEN [Fatura Tarihi] >= @Start_Date_1 AND [Fatura Tarihi] <= @End_Date_1 THEN S.Miktar ELSE 0 END)/NULLIF(DATEDIFF(MONTH, k.new_ilkyayintarihi, GETDATE()), 0)) * 0.4) + (SUM(CASE WHEN [Fatura Tarihi] >= DATEADD(MONTH, 1, k.new_ilkyayintarihi) THEN S.Miktar ELSE 0 END)/NULLIF(DATEDIFF(MONTH, k.new_ilkyayintarihi, GETDATE()),0) * 0.6) AS SatisHiziTahmini
    FROM [V_SatisRaporu_2025_2026] as S
    JOIN CRMDATABASE.[Timas_MSCRM].[dbo].[new_kitap] as K ON S.[Malzeme/Hizmet Kodu] = K.new_stokkodu COLLATE SQL_Latin1_General_CP1_CI_AS
    WHERE k.new_ilkyayintarihi >= DATEADD(MONTH, -12, DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()), 0))
    --AND k.new_ilkyayintarihi < DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()), 0)
    AND DATEDIFF(MONTH, k.new_ilkyayintarihi, GETDATE()) IS NOT NULL
    GROUP BY K.new_stokkodu, k.new_ilkyayintarihi
),
SecondQuery AS (
    SELECT *, ((COALESCE([1], 0) + COALESCE([2], 0) + COALESCE([3], 0) + COALESCE([4], 0) +
    COALESCE([5], 0) + COALESCE([6], 0) + COALESCE([7], 0) + COALESCE([8], 0) +
    COALESCE([9], 0) + COALESCE([10], 0) + COALESCE([11], 0) + COALESCE([12], 0))) AS ToplamSatis
    FROM
    ( SELECT [Malzeme/Hizmet Kodu], Ay, SUM(Miktar) as ToplamMiktar
      FROM [V_SatisRaporu_2025_2026] 
      GROUP BY [Malzeme/Hizmet Kodu], Ay ) AS tablom
    PIVOT ( SUM(ToplamMiktar) FOR Ay IN ([1], [2], [3],[4],[5],[6],[7],[8],[9],[10],[11],[12]) ) AS pivotTablom
)

SELECT *
FROM FirstQuery
JOIN SecondQuery ON FirstQuery.new_stokkodu = SecondQuery.[Malzeme/Hizmet Kodu] COLLATE SQL_Latin1_General_CP1_CI_AS"]),
    #"Birleştirilen Sorgular" = Table.NestedJoin(Kaynak, {"Malzeme/Hizmet Kodu"}, CRM_KitapDetay, {"StokKodu"}, "CRM_KitapDetay", JoinKind.LeftOuter),
    #"Birleştirilen Sorgular1" = Table.NestedJoin(#"Birleştirilen Sorgular", {"new_stokkodu"}, CRM_YeniKitapDetay, {"StokKodu"}, "CRM_YeniKitapDetay", JoinKind.LeftOuter),
    #"Genişletilen CRM_YeniKitapDetay" = Table.ExpandTableColumn(#"Birleştirilen Sorgular1", "CRM_YeniKitapDetay", {"StokAdedi"}, {"CRM_YeniKitapDetay.StokAdedi"})
in
    #"Genişletilen CRM_YeniKitapDetay"
