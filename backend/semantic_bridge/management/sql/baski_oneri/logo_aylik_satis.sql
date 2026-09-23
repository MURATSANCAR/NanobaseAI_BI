-- Son 12 ay (bu ay dahil), stok kodu × takvim ayı satış adedi.
-- Ay numarası 1–12; aynı ay iki yıldan gelemez çünkü pencere 12 aydır.
-- Pencere görünümün Yıl/Ay kolonlarıyla seçilir; fatura tarihi aralığıyla aynı satırlar, 7 kat hızlı
-- (ölçüm 2026-09-23: 79,6 sn → 12,2 sn, 54.023 satır birebir).
SELECT
    s.[Malzeme/Hizmet Kodu] AS stok_kodu,
    s.[Ay]                  AS ay,
    SUM(s.Miktar)           AS miktar
FROM {satis:-1} AS s  -- geçen yıl ve bu yılın satış görünümleri
WHERE s.[Yıl] * 12 + s.[Ay] >= YEAR(GETDATE()) * 12 + MONTH(GETDATE()) - 11
  AND s.[Malzeme/Hizmet Kodu] <> '15752.02.051'
GROUP BY s.[Malzeme/Hizmet Kodu], s.[Ay]
