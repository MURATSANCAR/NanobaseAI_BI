-- M52 Tek tedarikçinin alış faturaları (tedarikçi sayfası). Tanım «satinalma» ile aynı (TRCODE 1/4, NETTOTAL KDV dahil).
SELECT inv.DATE_ AS tarih, inv.FICHENO AS no, inv.TRCODE AS tur, inv.NETTOTAL AS tutar, inv.TOTALVAT AS kdv,
  inv.GENEXP1 AS aciklama
FROM dbo.LG_{firma}_{donem}_INVOICE inv
JOIN dbo.LG_{firma}_CLCARD C ON C.LOGICALREF = inv.CLIENTREF
WHERE inv.CANCELLED = 0 AND inv.TRCODE IN (1, 4) AND C.CODE = '{cari_kod}' AND inv.DATE_ >= '{bas}'
