-- Yeni kitapların (ilk yayını son 12 ay içinde) gün bazında satışı.
-- stok_kodlari yer tutucusu CRM'deki yeni kitap listesinden doldurulur; kodlar tırnak kaçışıyla eklenir.
-- Pencere (içinde bulunulan aydan 12 ay önceki ayın başı) görünümün Yıl/Ay kolonlarıyla seçilir.
SELECT
    s.[Malzeme/Hizmet Kodu]           AS stok_kodu,
    CAST(s.[Fatura Tarihi] AS DATE)   AS gun,
    SUM(s.Miktar)                     AS miktar
FROM {satis:-1} AS s  -- geçen yıl ve bu yılın satış görünümleri
WHERE s.[Yıl] * 12 + s.[Ay] >= YEAR(GETDATE()) * 12 + MONTH(GETDATE()) - 12
  AND s.[Malzeme/Hizmet Kodu] IN ({stok_kodlari})
GROUP BY s.[Malzeme/Hizmet Kodu], CAST(s.[Fatura Tarihi] AS DATE)
