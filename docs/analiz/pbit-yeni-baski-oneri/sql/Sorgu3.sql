-- Tablo: Sorgu3
-- Sunucu: 192.168.0.25  Veritabanı: LOGO_DB
-- Kaynak: 2025_Yeni_Baskı Öneri Raporu (5).pbit (Power Query'den çözüldü)

DECLARE @Bugun      date = GETDATE();
DECLARE @Start_Date date = DATEADD(MONTH, DATEDIFF(MONTH, 0, @Bugun) - 11, 0); -- 12 ay önce (ayın 1'i)
DECLARE @End_Date   date = EOMONTH(@Bugun);                                    -- Bu ayın sonu

SELECT 
    pvt.[Malzeme/Hizmet Kodu],
    ISNULL(pvt.[1],  0) AS Ocak,   -- Ocak
    ISNULL(pvt.[2],  0) AS Şubat,   -- Şubat
    ISNULL(pvt.[3],  0) AS Mart,
    ISNULL(pvt.[4],  0) AS Nisan,
    ISNULL(pvt.[5],  0) AS Mayis,
    ISNULL(pvt.[6],  0) AS Haziran,
    ISNULL(pvt.[7],  0) AS Temmuz,
    ISNULL(pvt.[8],  0) AS Agustos,
    ISNULL(pvt.[9],  0) AS Eylül,
    ISNULL(pvt.[10], 0) AS Ekim,
    ISNULL(pvt.[11], 0) AS Kasım,
    ISNULL(pvt.[12], 0) AS Aralık
FROM (
    SELECT  
        [Malzeme/Hizmet Kodu],
        Ay,
        SUM(Miktar) AS ToplamMiktar
    FROM V_SatisRaporu_ALL2
    WHERE [Malzeme/Hizmet Kodu] <> '15752.02.051'
      AND DATEFROMPARTS(Yıl, Ay, 1) BETWEEN @Start_Date AND @End_Date  -- <<< sadece son 12 ay
    GROUP BY [Malzeme/Hizmet Kodu], Ay
) AS tablom
PIVOT (
    SUM(ToplamMiktar) FOR Ay IN ([1],[2],[3],[4],[5],[6],[7],[8],[9],[10],[11],[12])
) AS pvt
ORDER BY [Malzeme/Hizmet Kodu];
