-- M44 Kargo: Logo'da gerçekleşen sevk (Kural 10): satış irsaliyesi satırları TRCODE 7,8, IOCODE 4, LINETYPE 0, CANCELLED 0.
-- Bir ayın irsaliye fişleri (satır ve adet) ve faturalanmış olanın fatura numarası. {f} = ayın yılının Logo firması.
SELECT S.STFICHEREF AS irsaliye, MAX(I.FICHENO) AS fatura_no, COUNT(*) AS satir, SUM(S.AMOUNT) AS adet
FROM dbo.LG_{f}_01_STLINE S
LEFT JOIN dbo.LG_{f}_01_INVOICE I ON I.LOGICALREF = S.INVOICEREF AND S.INVOICEREF <> 0
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.TRCODE IN (7,8) AND S.IOCODE = 4
  AND S.DATE_ >= '{bas}' AND S.DATE_ < '{bit}'
GROUP BY S.STFICHEREF
