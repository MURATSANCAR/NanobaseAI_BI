-- M42 (ve M34 pazar yeri sell-in) cari × ay: kanal kapsamındaki cariler. Sell-in: kanala faturalanan, kanalın sattığı değil.
-- {grup}: bir satırın hangi gruba düştüğü — tek tek eşlenen ya da e-ticaret kodlu cari kendi kodu, kanal koduyla
-- eşlenen cariler (ör. bireysel site müşterileri) '#K:<özel kod 2>'. {scope}: kapsam koşulu.
SELECT {grup} AS grup, MONTH(S.DATE_) AS ay,
{metrics}
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
WHERE S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.LINETYPE IN (0, 2) AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{year}-01-01' AND S.DATE_ < '{next}-01-01'
  AND ({scope})
GROUP BY {grup}, MONTH(S.DATE_)
