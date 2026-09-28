-- Logo bekleyen (açık) satış siparişi — katalog tanımı (metrics/logo-timas.md): ORFLINE TRCODE 1, CLOSED 0,
-- CANCELLED 0, LINETYPE 0; bekleyen = AMOUNT − SHIPPEDAMOUNT. Güncel yıl kopyası. CRM bekleyen siparişinin yanında ayrı gösterilir.
SELECT I.CODE AS stok_kodu, SUM(O.AMOUNT - O.SHIPPEDAMOUNT) AS bekleyen, COUNT(DISTINCT O.ORDFICHEREF) AS siparis
FROM dbo.LG_{firma}_01_ORFLINE AS O
JOIN dbo.LG_{firma}_ITEMS AS I ON I.LOGICALREF = O.STOCKREF
WHERE O.TRCODE = 1 AND O.CLOSED = 0 AND O.CANCELLED = 0 AND O.LINETYPE = 0
GROUP BY I.CODE
