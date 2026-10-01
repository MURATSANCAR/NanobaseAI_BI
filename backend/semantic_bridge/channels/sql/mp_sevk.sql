-- Aşama 0: konsinye izi. Pazar yeri carilerine faturalanmamış satış irsaliyesi (TRCODE 8) ve satış iade irsaliyesi
-- (TRCODE 3): INVOICEREF = 0 ve BILLED = 0 (Kural 18). {eski} tarihinden önceki açık sevk «eski açık sevk»tir.
SELECT C.CODE AS cari, S.TRCODE AS tur, MONTH(S.DATE_) AS ay, COUNT(*) AS satir, SUM(S.AMOUNT) AS adet,
  SUM(CASE WHEN S.DATE_ < '{eski}' THEN 1 ELSE 0 END) AS eski_satir,
  SUM(CASE WHEN S.DATE_ < '{eski}' THEN S.AMOUNT ELSE 0 END) AS eski_adet
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF = 0 AND S.BILLED = 0 AND S.TRCODE IN (3, 8)
  AND S.DATE_ >= '{bas}' AND S.DATE_ < '{bit}'
  AND C.CODE IN ({codes})
GROUP BY C.CODE, S.TRCODE, MONTH(S.DATE_)
