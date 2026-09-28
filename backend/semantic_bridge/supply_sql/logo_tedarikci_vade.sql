-- M52 Tedarikçi ödeme planı satırları (Logo PAYTRANS, SIGN 1 = bizim ödeyeceğimiz), bakiyesi pozitif cariler.
-- Logo'da ödeme kapama kullanılmıyor: hangi satırın ödendiği bilinmez. FIFO yaklaşımı (katalog
-- «satici-borcu-yaslandirma-fifo»): bakiye en yeni vadeli satırdan geriye dağıtılır, eski satırlar ödenmiş sayılır.
-- `kumulatif` en yeni satırdan geriye birikimli toplamdır; açık kalan tutar köprüde bu kolonla hesaplanır.
WITH B AS (
  SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN = 1 THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
  FROM dbo.LG_{firma}_{donem}_CLFLINE L JOIN dbo.LG_{firma}_CLCARD C ON C.LOGICALREF = L.CLIENTREF
  WHERE L.CANCELLED = 0 AND C.CODE LIKE '{on_ek}%' AND L.DATE_ >= '{yil_basi}'
  GROUP BY L.CLIENTREF
)
SELECT P.CARDREF AS ref, P.LOGICALREF AS satir, P.DATE_ AS vade, P.TOTAL AS tutar,
  SUM(P.TOTAL) OVER (PARTITION BY P.CARDREF ORDER BY P.DATE_ DESC, P.LOGICALREF DESC ROWS UNBOUNDED PRECEDING) AS kumulatif,
  I.FICHENO AS fatura_no, I.DATE_ AS fatura_tarihi
FROM dbo.LG_{firma}_{donem}_PAYTRANS P
LEFT JOIN dbo.LG_{firma}_{donem}_INVOICE I ON P.MODULENR = 4 AND I.LOGICALREF = P.FICHEREF
WHERE P.CANCELLED = 0 AND P.SIGN = 1 AND P.CARDREF IN (SELECT CLIENTREF FROM B WHERE bakiye > 0)
