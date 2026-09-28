-- M52 Üretimden giriş (basılan adet), ay bazında (Logo, yalnız okuma). Kural 20 «üretilen adet»: STLINE TRCODE 13,
-- IOCODE 1, malzeme satırı. M12 ölçümüyle (2026-09-28) fiş PRODSTAT 0 = gerçek giriş, 1 = planlanan giriş (ileri
-- tarihli, emir başına bir fiş); planlanan sayılmaz — ikisi toplanırsa basılan adet şişer.
SELECT YEAR(f.DATE_) AS yil, MONTH(f.DATE_) AS ay, SUM(l.AMOUNT) AS adet, COUNT(DISTINCT f.LOGICALREF) AS fis
FROM dbo.LG_{firma}_{donem}_STFICHE f
JOIN dbo.LG_{firma}_{donem}_STLINE l ON l.STFICHEREF = f.LOGICALREF
WHERE f.TRCODE = 13 AND f.CANCELLED = 0 AND f.PRODSTAT = 0 AND l.TRCODE = 13 AND l.IOCODE = 1 AND l.LINETYPE = 0
  AND l.CANCELLED = 0 AND f.DATE_ >= '{bas}'
GROUP BY YEAR(f.DATE_), MONTH(f.DATE_)
