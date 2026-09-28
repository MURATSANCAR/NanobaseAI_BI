-- M41 döviz faturaları (kabul 6): yıl içinde işlem dövizi TL olmayan (TRCURR NOT IN 0, 160) iptal edilmemiş faturalar.
-- «toplam» bütün fatura türleri (katalog notundaki 74 sayısının olası yöntemi), «satis» yalnız satış faturası (7,8,9).
SELECT COUNT(*) AS toplam,
  SUM(CASE WHEN F.TRCODE IN (7,8,9) THEN 1 ELSE 0 END) AS satis,
  SUM(CASE WHEN F.TRCODE IN (7,8,9) THEN F.NETTOTAL ELSE 0 END) AS satis_tl
FROM dbo.LG_{firm}_01_INVOICE AS F
WHERE F.CANCELLED = 0 AND ISNULL(F.TRCURR, 0) NOT IN (0, 160)
  AND F.DATE_ >= '{year}-01-01' AND F.DATE_ < '{next}-01-01'
