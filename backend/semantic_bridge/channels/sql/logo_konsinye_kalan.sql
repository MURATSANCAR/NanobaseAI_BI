-- M41 konsinye kalan (kabul 3): onaylı Amazon carilerine faturalanmamış satış irsaliyesi (TRCODE 8) ve faturalanmamış
-- satış iade irsaliyesi (TRCODE 3), kitap bazında (Kural 18: INVOICEREF = 0 ve BILLED = 0). Kalan = sevk − iade; iade
-- ekranda ayrıca yazar. Faturalanan sevk M42 kanal karnesindedir (faturalı satır). {codes}: onaylı Amazon cari kodları —
-- kod ile süzülür, çünkü yıl kopyasında LOGICALREF değişebilir.
SELECT C.CODE AS cari, I.CODE AS stok_kodu,
  SUM(CASE WHEN S.TRCODE = 8 THEN S.AMOUNT ELSE 0 END) AS sevk,
  SUM(CASE WHEN S.TRCODE = 3 THEN S.AMOUNT ELSE 0 END) AS iade,
  SUM(CASE WHEN S.TRCODE = 8 THEN S.LINENET ELSE 0 END) AS sevk_tutar,
  MIN(S.DATE_) AS ilk, MAX(S.DATE_) AS son
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF = 0 AND S.BILLED = 0 AND S.TRCODE IN (3, 8)
  AND S.DATE_ >= '{year}-01-01' AND S.DATE_ < '{next}-01-01'
  AND C.CODE IN ({codes})
GROUP BY C.CODE, I.CODE
