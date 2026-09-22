-- Yeni kitapların (ilk yayını son 12 ay içinde) gün bazında satışı.
-- {stok_kodlari} CRM'deki yeni kitap listesinden doldurulur; kodlar tırnak kaçışıyla eklenir.
SELECT
    s.[Malzeme/Hizmet Kodu]           AS stok_kodu,
    CAST(s.[Fatura Tarihi] AS DATE)   AS gun,
    SUM(s.Miktar)                     AS miktar
FROM dbo.V_SatisRaporu_All2 AS s
WHERE s.[Fatura Tarihi] >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) - 12, 0)
  AND s.[Malzeme/Hizmet Kodu] IN ({stok_kodlari})
GROUP BY s.[Malzeme/Hizmet Kodu], CAST(s.[Fatura Tarihi] AS DATE)
