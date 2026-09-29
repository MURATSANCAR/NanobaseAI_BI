-- Aşama 0: pazar yeri carilerinin cari hesap hareketleri (para nasıl geliyor: havale, virman, dekont, çek…).
-- MODULENR 4 fatura, 5 cari fiş, 6 çek/senet, 7 banka, 10 kasa; SIGN 0 borç, 1 alacak. İptal hariç.
SELECT C.CODE AS cari, L.MODULENR AS modul, L.TRCODE AS tur, L.SIGN AS yon, MONTH(L.DATE_) AS ay,
  COUNT(*) AS hareket, SUM(L.AMOUNT) AS tutar
FROM dbo.LG_{firm}_01_CLFLINE AS L
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = L.CLIENTREF
WHERE L.CANCELLED = 0 AND L.DATE_ >= '{bas}' AND L.DATE_ < '{bit}'
  AND C.CODE IN ({codes})
GROUP BY C.CODE, L.MODULENR, L.TRCODE, L.SIGN, MONTH(L.DATE_)
