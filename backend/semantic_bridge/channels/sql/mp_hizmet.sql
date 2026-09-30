-- Aşama 0: pazar yeri carileriyle hizmet satırları (LINETYPE 4) hizmet kartıyla — kesinti (komisyon, kargo, hizmet
-- bedeli, reklam, stopaj) Logo'da hizmet faturası olarak mı giriyor? Alış tarafı (TRCODE 1, 4) kesinti adayıdır.
SELECT C.CODE AS cari, S.TRCODE AS tur, SV.CODE AS hizmet_kodu, SV.DEFINITION_ AS hizmet, MONTH(S.DATE_) AS ay,
  COUNT(*) AS satir, SUM(S.LINENET) AS tutar
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_SRVCARD AS SV ON SV.LOGICALREF = S.STOCKREF
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
WHERE S.LINETYPE = 4 AND S.CANCELLED = 0 AND S.DATE_ >= '{bas}' AND S.DATE_ < '{bit}'
  AND C.CODE IN ({codes})
GROUP BY C.CODE, S.TRCODE, SV.CODE, SV.DEFINITION_, MONTH(S.DATE_)
