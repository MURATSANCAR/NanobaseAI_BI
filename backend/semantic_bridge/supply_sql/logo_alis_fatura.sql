-- M52 Tedarikçi carilerinin alış faturaları, cari × ay (Logo, yalnız okuma). Katalog «satinalma» ölçüsüyle aynı:
-- Σ NETTOTAL, TRCODE 1 (mal alımı) ve 4 (alınan hizmet), iptal hariç. NETTOTAL KDV dahildir.
SELECT C.CODE AS cari_kod, YEAR(inv.DATE_) AS yil, MONTH(inv.DATE_) AS ay, inv.TRCODE AS tur,
  COUNT(*) AS fatura, SUM(inv.NETTOTAL) AS tutar, SUM(inv.TOTALVAT) AS kdv
FROM dbo.LG_{firma}_{donem}_INVOICE inv
JOIN dbo.LG_{firma}_CLCARD C ON C.LOGICALREF = inv.CLIENTREF
WHERE inv.CANCELLED = 0 AND inv.TRCODE IN (1, 4) AND C.CODE LIKE '{on_ek}%' AND inv.DATE_ >= '{bas}'
GROUP BY C.CODE, YEAR(inv.DATE_), MONTH(inv.DATE_), inv.TRCODE
