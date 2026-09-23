-- Yeni kitapların (ilk yayını son 12 ay içinde) gün bazında satışı.
-- Kod listesi CRM'deki yeni kitaplardan doldurulur (tırnak kaçışıyla) ve bir VALUES tablosu olarak
-- birleştirilir: aynı kodları IN listesiyle seçmek planı bozup süreyi 14 sn'den 194 sn'ye çıkarıyordu.
-- Pencere (içinde bulunulan aydan 12 ay önceki ayın başı) görünümün Yıl/Ay kolonlarıyla seçilir.
SELECT
    s.[Malzeme/Hizmet Kodu]           AS stok_kodu,
    CAST(s.[Fatura Tarihi] AS DATE)   AS gun,
    SUM(s.Miktar)                     AS miktar
FROM {satis:-1} AS s  -- geçen yıl ve bu yılın satış görünümleri
JOIN (VALUES {stok_kodlari_satirlari}) AS kod(k) ON kod.k = s.[Malzeme/Hizmet Kodu]
WHERE s.[Yıl] * 12 + s.[Ay] >= YEAR(GETDATE()) * 12 + MONTH(GETDATE()) - 12
GROUP BY s.[Malzeme/Hizmet Kodu], CAST(s.[Fatura Tarihi] AS DATE)
