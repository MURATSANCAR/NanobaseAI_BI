-- Barkod → stok kodu: site siparişi satırını (barkodlu) Logo kitabına bağlamak için (D2C sekmesi).
SELECT I.CODE AS stok_kodu, B.BARCODE AS barkod
FROM dbo.LG_{firm}_UNITBARCODE AS B
JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = B.ITEMREF
WHERE B.BARCODE IS NOT NULL AND LTRIM(RTRIM(B.BARCODE)) <> ''
