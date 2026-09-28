-- M42 kanal karnesi, kanal (cari özel kodu 2) × ay: bütün cariler. Kanallar arası kıyasın tabanı (kitapçı, e-ticaret…).
-- Yer tutucular: {firm} yılın Logo firma numarası, {year}/{next} takvim yılı sınırı; ölçü kolonları _metrics.sql'den gelir.
-- (Çok satırlı ölçü yer tutucusu yorum satırında anılmaz: yerine konunca ilk satırından sonrası yorum dışında kalır.)
SELECT ISNULL(NULLIF(LTRIM(RTRIM(C.SPECODE2)), ''), '#YOK') AS kanal, MONTH(S.DATE_) AS ay,
{metrics}
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
WHERE S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.LINETYPE IN (0, 2) AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{year}-01-01' AND S.DATE_ < '{next}-01-01'
GROUP BY ISNULL(NULLIF(LTRIM(RTRIM(C.SPECODE2)), ''), '#YOK'), MONTH(S.DATE_)
