-- Baskı Öneri'deki kitapların 2015'ten bu yana aylık satış adedi (tahminin geçmişi).
-- Satırlar Power BI'ın okuduğu kaynakla aynıdır: Logo yıllık satış görünümleri (V_SatisRaporu_ALL2'nin kolları).
-- Kod listesi Baskı Öneri raporundan gelir ve VALUES tablosu olarak birleştirilir.
SELECT
    s.[Malzeme/Hizmet Kodu] AS stok_kodu,
    s.[Yıl]                 AS yil,
    s.[Ay]                  AS ay,
    SUM(s.Miktar)           AS miktar
FROM {satis:2015} AS s  -- 2015'ten bu yılın sonuna yıllık satış görünümleri
JOIN (VALUES {stok_kodlari_satirlari}) AS kod(k) ON kod.k = s.[Malzeme/Hizmet Kodu]
GROUP BY s.[Malzeme/Hizmet Kodu], s.[Yıl], s.[Ay]
