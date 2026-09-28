-- M41 yurtdışı karnesi (kabul 5): yurtdışı kanal kodlu carilere faturalı satış/iade, cari × ülke × döviz × ay.
-- Tanım M42 ile aynı: faturalı malzeme satırı, TRCODE 7,8,9 satış − 2,3 iade, LINENET (TL). Döviz tutarı faturanın
-- işlem dövizinden: TRCURR 0/160 = TL; diğerinde LINENET ÷ TRRATE (fatura kuru). {specodes}: Yönetim ayarı
-- AMAZON_YURTDISI_KODLARI (yazımı önce `SELECT DISTINCT SPECODE2` ile ölçülür).
SELECT C.CODE AS cari, MAX(C.DEFINITION_) AS unvan, C.COUNTRY AS ulke, ISNULL(F.TRCURR, 0) AS doviz, MONTH(S.DATE_) AS ay,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE 0 END) AS satis_ciro,
  SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.LINENET ELSE 0 END) AS iade_ciro,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE 0 END) AS satis_adet,
  SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.AMOUNT ELSE 0 END) AS iade_adet,
  SUM(CASE WHEN ISNULL(F.TRCURR, 0) NOT IN (0, 160) AND ISNULL(F.TRRATE, 0) > 0
           THEN (CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) / F.TRRATE ELSE 0 END) AS doviz_net,
  COUNT(DISTINCT S.INVOICEREF) AS fatura
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
JOIN dbo.LG_{firm}_01_INVOICE AS F ON F.LOGICALREF = S.INVOICEREF
WHERE S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.LINETYPE = 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{year}-01-01' AND S.DATE_ < '{next}-01-01'
  AND C.SPECODE2 IN ({specodes})
GROUP BY C.CODE, C.COUNTRY, ISNULL(F.TRCURR, 0), MONTH(S.DATE_)
