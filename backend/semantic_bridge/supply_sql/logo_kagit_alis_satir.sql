-- M52 Kağıtçı carilerinden mal alımı satırları (Logo, TRCODE 1, malzeme satırı): kağıt alış fiyatı eğilimi.
-- Birim fiyat = satır net tutarı ÷ miktar (KDV hariç); birim, satırın ölçü biriminden (kg, tabaka…) okunur.
-- Kağıtçı cari listesi köprüden gelir (özel kod ya da tedarikçi eşlemesi).
SELECT inv.DATE_ AS tarih, C.CODE AS cari_kod, I.CODE AS malzeme_kod, I.NAME AS malzeme, U.CODE AS birim,
  l.AMOUNT AS miktar, l.LINENET AS tutar
FROM dbo.LG_{firma}_{donem}_INVOICE inv
JOIN dbo.LG_{firma}_{donem}_STLINE l ON l.INVOICEREF = inv.LOGICALREF
JOIN dbo.LG_{firma}_ITEMS I ON I.LOGICALREF = l.STOCKREF
JOIN dbo.LG_{firma}_CLCARD C ON C.LOGICALREF = inv.CLIENTREF
JOIN (VALUES {kodlar}) AS k(kod) ON k.kod = C.CODE
LEFT JOIN dbo.LG_{firma}_UNITSETL U ON U.LOGICALREF = l.UOMREF
WHERE inv.CANCELLED = 0 AND inv.TRCODE = 1 AND l.LINETYPE = 0 AND l.CANCELLED = 0 AND inv.DATE_ >= '{bas}'
