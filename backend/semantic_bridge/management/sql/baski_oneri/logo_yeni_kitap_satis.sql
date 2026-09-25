-- Yeni kitapların (ilk yayını son 12 ay içinde) gün bazında satışı.
-- Kod listesi CRM'deki yeni kitaplardan doldurulur (tırnak kaçışıyla) ve bir VALUES tablosu olarak
-- birleştirilir: aynı kodları IN listesiyle seçmek planı bozup süreyi 14 sn'den 194 sn'ye çıkarıyordu.
-- Geçen yılın ve bu yılın tamamı okunur (mevcut rapor: V_SatisRaporu_2025_2026). Ay kolonları iki yılın aynı
-- ayını toplar; yayından önceki satış da o aya düşer. Son 1 yıl, RPT, dağılım pencereleri hesapta süzülür.
SELECT
    s.[Malzeme/Hizmet Kodu]           AS stok_kodu,
    CAST(s.[Fatura Tarihi] AS DATE)   AS gun,
    SUM(s.Miktar)                     AS miktar
FROM {satis:-1} AS s  -- geçen yıl ve bu yılın satış görünümleri
JOIN (VALUES {stok_kodlari_satirlari}) AS kod(k) ON kod.k = s.[Malzeme/Hizmet Kodu]
GROUP BY s.[Malzeme/Hizmet Kodu], CAST(s.[Fatura Tarihi] AS DATE)
