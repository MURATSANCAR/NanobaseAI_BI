-- Kitap başına aylık satış adedi, bir yıl için. Tahmin raporu bunu 2015'ten bu yıla her yıl ayrı çalıştırır:
-- 12 yılın birleşimini tek sorguda gruplamak 900 sn'yi aşıyordu, yıl başına görünüm 10–50 sn.
-- Satırlar Power BI'ın okuduğu kaynakla aynıdır (V_SatisRaporu_ALL2'nin o yılki kolu, aynı süzgeç).
SELECT
    s.[Malzeme/Hizmet Kodu] AS stok_kodu,
    s.[Yıl]                 AS yil,
    s.[Ay]                  AS ay,
    SUM(s.Miktar)           AS miktar
FROM {satis:yil} AS s
GROUP BY s.[Malzeme/Hizmet Kodu], s.[Yıl], s.[Ay]
