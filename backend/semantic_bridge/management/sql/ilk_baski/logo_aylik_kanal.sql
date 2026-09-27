-- Kitap × ay × kanal satışı, bir yıl için. Rapor bunu 2015'ten bu yıla her yıl ayrı çalıştırır (yıllık görünüm,
-- Baskı Öneri tahmin sekmesiyle aynı yol). Satırlar Baskı Öneri'nin okuduğu satırlardır (aynı görünüm, aynı süzgeç);
-- adet net satıştır (iade eksi). Kanal Logo'nun KANAL alanıdır; boş kanallı perakende faturası «PERAKENDE» sayılır.
-- liste_tutar = adet × birim (liste) fiyat: net tutarın liste fiyatına oranı kanal iskontosunu verir.
SELECT
    s.[Malzeme/Hizmet Kodu] AS stok_kodu,
    s.[Yıl]                 AS yil,
    s.[Ay]                  AS ay,
    COALESCE(NULLIF(LTRIM(RTRIM(s.KANAL)), ''),
             CASE WHEN s.[Fatura Türü] LIKE N'Perakende%' THEN 'PERAKENDE' ELSE 'DIGER' END) AS kanal,
    SUM(s.Miktar)                   AS miktar,
    SUM(s.[Net Tutar])              AS net_tutar,
    SUM(s.Miktar * s.[Birim Fiyat]) AS liste_tutar
FROM {satis:yil} AS s
GROUP BY s.[Malzeme/Hizmet Kodu], s.[Yıl], s.[Ay],
         COALESCE(NULLIF(LTRIM(RTRIM(s.KANAL)), ''),
                  CASE WHEN s.[Fatura Türü] LIKE N'Perakende%' THEN 'PERAKENDE' ELSE 'DIGER' END)
