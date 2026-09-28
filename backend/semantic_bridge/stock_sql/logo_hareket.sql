-- Pencere içinde hareketi olan malzemeler (Kural 17: dönemde STLINE satırı, CANCELLED 0, LINETYPE 0). Açılış devri
-- (TRCODE 14) hareket sayılmaz: her yıl başında stoklu her malzemeye yazılır, sayılırsa hiçbir kitap hareketsiz çıkmaz.
-- Net satış = faturalı satış satırı (TRCODE 7,8,9, INVOICEREF <> 0) − faturalı iade (TRCODE 2,3).
-- Pencere birden çok yıla düşerse her yıl kopyası ayrı okunur ve birleştirilir.
SELECT I.CODE AS stok_kodu, MAX(L.DATE_) AS son_hareket,
  SUM(CASE WHEN L.TRCODE IN (7,8,9) AND L.INVOICEREF <> 0 THEN L.AMOUNT
           WHEN L.TRCODE IN (2,3) AND L.INVOICEREF <> 0 THEN -L.AMOUNT ELSE 0 END) AS net_satis
FROM dbo.LG_{firma}_01_STLINE AS L
JOIN dbo.LG_{firma}_ITEMS AS I ON I.LOGICALREF = L.STOCKREF
{planli_join}
WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.TRCODE <> 14 {planli_kosul}
  AND L.DATE_ >= '{bas}' AND L.DATE_ < '{bitis}'
GROUP BY I.CODE
