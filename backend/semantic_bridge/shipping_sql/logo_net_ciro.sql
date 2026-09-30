-- M44 Kargo maliyeti: cironun yüzdesi için ay ay net ciro. Satış faturaları (7, 8, 9) eksi iade faturaları (2, 3),
-- iptal hariç; KDV hariç = NETTOTAL − TOTALVAT. En son fatura tarihi ekranın veri sonudur.
SELECT MONTH(I.DATE_) AS ay,
  SUM(CASE WHEN I.TRCODE IN (7,8,9) THEN I.NETTOTAL - I.TOTALVAT ELSE 0 END) AS satis,
  SUM(CASE WHEN I.TRCODE IN (2,3) THEN I.NETTOTAL - I.TOTALVAT ELSE 0 END) AS iade,
  MAX(I.DATE_) AS son
FROM dbo.LG_{f}_01_INVOICE I
WHERE I.CANCELLED = 0 AND I.TRCODE IN (2,3,7,8,9) AND I.DATE_ >= '{bas}' AND I.DATE_ < '{bit}'
GROUP BY MONTH(I.DATE_)
