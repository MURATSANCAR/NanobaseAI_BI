-- Aşama 0: pazar yeri carilerinin satış/iade faturalarında belge alanlarının doluluğu (platform sipariş numarası hangi
-- alanda taşınıyor olabilir). Değer okunmaz, yalnız dolu fatura sayısı.
SELECT F.TRCODE AS tur, COUNT(*) AS fatura,
  SUM(CASE WHEN LTRIM(RTRIM(ISNULL(F.DOCODE, ''))) <> '' THEN 1 ELSE 0 END) AS docode,
  SUM(CASE WHEN LTRIM(RTRIM(ISNULL(F.SPECODE, ''))) <> '' THEN 1 ELSE 0 END) AS specode,
  SUM(CASE WHEN LTRIM(RTRIM(ISNULL(F.CYPHCODE, ''))) <> '' THEN 1 ELSE 0 END) AS cyphcode,
  SUM(CASE WHEN LTRIM(RTRIM(ISNULL(F.GENEXP1, ''))) <> '' THEN 1 ELSE 0 END) AS genexp1,
  SUM(CASE WHEN LTRIM(RTRIM(ISNULL(F.GENEXP2, ''))) <> '' THEN 1 ELSE 0 END) AS genexp2,
  SUM(CASE WHEN LTRIM(RTRIM(ISNULL(F.GENEXP3, ''))) <> '' THEN 1 ELSE 0 END) AS genexp3,
  SUM(CASE WHEN LTRIM(RTRIM(ISNULL(F.GENEXP4, ''))) <> '' THEN 1 ELSE 0 END) AS genexp4,
  SUM(CASE WHEN LTRIM(RTRIM(ISNULL(F.DOCTRACKINGNR, ''))) <> '' THEN 1 ELSE 0 END) AS doctrackingnr
FROM dbo.LG_{firm}_01_INVOICE AS F
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = F.CLIENTREF
WHERE F.CANCELLED = 0 AND F.TRCODE IN (2, 3, 7, 8, 9) AND F.DATE_ >= '{bas}' AND F.DATE_ < '{bit}'
  AND C.CODE IN ({codes})
GROUP BY F.TRCODE
