-- Aşama 0: belge alanında platform adı geçen satış/iade faturaları (tüketiciye kesilen e-arşiv faturası platform adını
-- açıklama/özel kod alanında taşıyabilir; cari tek tek tüketicidir). Kaç farklı cariye, hangi kanal koduyla.
-- {kosul}: Yönetim ayarındaki adların belge alanlarında (DOCODE, SPECODE, CYPHCODE, GENEXP1–4) aranması.
SELECT F.TRCODE AS tur, C.SPECODE2 AS kanal, MONTH(F.DATE_) AS ay, COUNT(*) AS fatura,
  COUNT(DISTINCT F.CLIENTREF) AS cari, SUM(F.NETTOTAL) AS tutar
FROM dbo.LG_{firm}_01_INVOICE AS F
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = F.CLIENTREF
WHERE F.CANCELLED = 0 AND F.TRCODE IN (2, 3, 7, 8, 9) AND F.DATE_ >= '{bas}' AND F.DATE_ < '{bit}'
  AND ({kosul})
GROUP BY F.TRCODE, C.SPECODE2, MONTH(F.DATE_)
