-- Son 12 ay (bu ay dahil), stok kodu × takvim ayı satış adedi.
-- Ay numarası 1–12; aynı ay iki yıldan gelemez çünkü pencere 12 aydır.
SELECT
    s.[Malzeme/Hizmet Kodu] AS stok_kodu,
    MONTH(s.[Fatura Tarihi]) AS ay,
    SUM(s.Miktar)            AS miktar
FROM dbo.V_SatisRaporu_All2 AS s
WHERE s.[Fatura Tarihi] >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - 11, 0)
  AND s.[Fatura Tarihi] <  DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) + 1, 0)
  AND s.[Malzeme/Hizmet Kodu] <> '15752.02.051'
GROUP BY s.[Malzeme/Hizmet Kodu], MONTH(s.[Fatura Tarihi])
