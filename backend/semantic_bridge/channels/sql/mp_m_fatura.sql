-- Aşama 1 (mutabakat): panel dosyalarının tarih aralığındaki faturalar (satış 7,8,9; iade 2,3; alış tarafı 1,4 —
-- kesinti faturası). Belge alanları yalnız bellekte, panel sipariş/belge numarasıyla eşleşme aramak için okunur; portala
-- yalnız eşleşen ya da pazar yeri carisine kesilen faturanın kimliği, türü, tarihi, tutarı ve eşleşen alan adı yazılır.
SELECT F.LOGICALREF AS ref, F.TRCODE AS tur, F.DATE_ AS tarih, F.NETTOTAL AS tutar, F.FICHENO AS ficheno,
  F.DOCODE AS docode, F.SPECODE AS specode, F.CYPHCODE AS cyphcode, F.GENEXP1 AS genexp1, F.GENEXP2 AS genexp2,
  F.GENEXP3 AS genexp3, F.GENEXP4 AS genexp4, F.DOCTRACKINGNR AS doctrackingnr, C.CODE AS cari, C.SPECODE2 AS kanal
FROM dbo.LG_{firm}_01_INVOICE AS F
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = F.CLIENTREF
WHERE F.CANCELLED = 0 AND F.TRCODE IN (1, 2, 3, 4, 7, 8, 9) AND F.DATE_ >= '{bas}' AND F.DATE_ < '{bit}'
