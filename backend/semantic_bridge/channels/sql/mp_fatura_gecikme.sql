-- Aşama 0: sevk → fatura gecikmesi. Faturalanmış satış irsaliyesi satırında (TRCODE 8) satırın (irsaliye) tarihi ile
-- faturanın tarihi arasındaki gün. Sevkle aynı gün faturalanan toptan satıştır; {gun} günden geç faturalanan sevk
-- «sattıkça faturala» (konsinye) izidir.
SELECT C.CODE AS cari, COUNT(*) AS satir,
  SUM(CASE WHEN DATEDIFF(DAY, S.DATE_, F.DATE_) > {gun} THEN 1 ELSE 0 END) AS gec_satir,
  SUM(CASE WHEN DATEDIFF(DAY, S.DATE_, F.DATE_) > {gun} THEN S.AMOUNT ELSE 0 END) AS gec_adet,
  MAX(DATEDIFF(DAY, S.DATE_, F.DATE_)) AS en_uzun_gun,
  COUNT(DISTINCT CASE WHEN DATEDIFF(DAY, S.DATE_, F.DATE_) > {gun} THEN MONTH(F.DATE_) END) AS gec_ay
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_01_INVOICE AS F ON F.LOGICALREF = S.INVOICEREF
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.TRCODE = 8 AND S.INVOICEREF <> 0 AND F.CANCELLED = 0
  AND F.DATE_ >= '{bas}' AND F.DATE_ < '{bit}'
  AND C.CODE IN ({codes})
GROUP BY C.CODE
