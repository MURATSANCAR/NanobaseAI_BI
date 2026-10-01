-- Aşama 1 (hakediş): pazar yeri carilerinin fatura dışı cari hareketleri (tahsilat, virman, dekont) gün × tür.
-- MODULENR 4 (fatura) hariç; SIGN 1 alacak (carinin bize ödemesi/mahsup), 0 borç.
SELECT C.CODE AS cari, L.MODULENR AS modul, L.TRCODE AS tur, L.SIGN AS yon, CAST(L.DATE_ AS DATE) AS tarih,
  COUNT(*) AS hareket, SUM(L.AMOUNT) AS tutar
FROM dbo.LG_{firm}_01_CLFLINE AS L
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = L.CLIENTREF
WHERE L.CANCELLED = 0 AND L.MODULENR <> 4 AND L.DATE_ >= '{bas}' AND L.DATE_ < '{bit}'
  AND C.CODE IN ({codes})
GROUP BY C.CODE, L.MODULENR, L.TRCODE, L.SIGN, CAST(L.DATE_ AS DATE)
