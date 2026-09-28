-- M52 Matbaa baskı faturası satırları (Logo, yalnız okuma). M12'deki tanımın aynısı: alınan hizmet faturası
-- (TRCODE 4), hizmet kartı «Komple Baskı Giderleri» ({baski_hizmeti}); satır özel kodu = kitabın stok kodu, miktar =
-- basılan adet, tutar = satır net tutarı (KDV hariç). Özel kodu boş satırlar da okunur: kuralın bağlayamadığı faturayı
-- «işi görünmeyen fatura» listesi gösterir. Faturayı kesen cari kodu (matbaa ↔ cari eşlemesi) buradan.
SELECT inv.LOGICALREF AS fatura_ref, inv.DATE_ AS tarih, inv.FICHENO AS no, c.CODE AS cari_kod, c.DEFINITION_ AS cari,
  l.LOGICALREF AS satir_ref, l.SPECODE AS stok, l.AMOUNT AS adet, l.LINENET AS tutar
FROM dbo.LG_{firma}_{donem}_INVOICE inv
JOIN dbo.LG_{firma}_{donem}_STLINE l ON l.INVOICEREF = inv.LOGICALREF
JOIN dbo.LG_{firma}_SRVCARD s ON s.LOGICALREF = l.STOCKREF
JOIN dbo.LG_{firma}_CLCARD c ON c.LOGICALREF = inv.CLIENTREF
WHERE inv.TRCODE = 4 AND inv.CANCELLED = 0 AND l.LINETYPE = 4 AND s.CODE = '{baski_hizmeti}'
  AND inv.DATE_ >= '{bas}'
