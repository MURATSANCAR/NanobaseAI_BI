-- Stok bakiyesi, malzeme × ambar (Logo Kural 14): güncel yılın kopyası, tarih süzgeci yok (açılış devri dahil).
-- Giriş IOCODE 1,2 − çıkış 3,4; LINETYPE 0 (malzeme satırı), CANCELLED 0. Kitap toplamı = ambarların toplamı.
-- Planlanan üretimden giriş fişi (STFICHE.PRODSTAT = 1, ileri tarihli) fiziksel stok değildir; ayarla dışarıda
-- (STOCK_EXCLUDE_PLANNED, varsayılan açık — M12/M29 ölçümü 2026-09-28).
SELECT I.CODE AS stok_kodu, MAX(I.NAME) AS ad, L.SOURCEINDEX AS ambar_no,
  SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
FROM dbo.LG_{firma}_01_STLINE AS L
JOIN dbo.LG_{firma}_ITEMS AS I ON I.LOGICALREF = L.STOCKREF
{planli_join}
WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.IOCODE IN (1,2,3,4) {planli_kosul}
GROUP BY I.CODE, L.SOURCEINDEX
