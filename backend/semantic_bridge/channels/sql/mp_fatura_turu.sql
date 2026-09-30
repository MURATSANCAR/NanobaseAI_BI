-- Aşama 0: pazar yeri carilerinin fatura türü dağılımı (TRCODE 1 mal alım, 2 perakende satış iadesi, 3 toptan satış
-- iadesi, 4 alınan hizmet, 6 alım iadesi, 7 perakende satış, 8 toptan satış, 9 verilen hizmet), cari × tür × ay.
-- Tutar NETTOTAL (KDV dahil net); döviz = TRCURR 0/160 dışı fatura. İptal hariç.
SELECT C.CODE AS cari, F.TRCODE AS tur, MONTH(F.DATE_) AS ay, COUNT(*) AS fatura, SUM(F.NETTOTAL) AS tutar,
  SUM(CASE WHEN ISNULL(F.TRCURR, 0) NOT IN (0, 160) THEN 1 ELSE 0 END) AS doviz
FROM dbo.LG_{firm}_01_INVOICE AS F
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = F.CLIENTREF
WHERE F.CANCELLED = 0 AND F.DATE_ >= '{bas}' AND F.DATE_ < '{bit}'
  AND C.CODE IN ({codes})
GROUP BY C.CODE, F.TRCODE, MONTH(F.DATE_)
