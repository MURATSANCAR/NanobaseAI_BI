-- M52 Tedarikçilerin alış faturaları (tedarikçi sayfası; okuma turunda bir kez, sayfa kendi carisini süzer).
-- Tanım `logo_tedarikci_faturalar.sql` ile aynı (TRCODE 1/4, NETTOTAL KDV dahil, iptal hariç); tek fark cari kodu
-- süzgeci: tek cari yerine {on_ek} ile başlayan bütün tedarikçi carileri, cari kodu kolonuyla.
SELECT C.CODE AS cari_kod, inv.DATE_ AS tarih, inv.FICHENO AS no, inv.TRCODE AS tur, inv.NETTOTAL AS tutar,
  inv.TOTALVAT AS kdv, inv.GENEXP1 AS aciklama
FROM dbo.LG_{firma}_{donem}_INVOICE inv
JOIN dbo.LG_{firma}_CLCARD C ON C.LOGICALREF = inv.CLIENTREF
WHERE inv.CANCELLED = 0 AND inv.TRCODE IN (1, 4) AND C.CODE LIKE '{on_ek}%' AND inv.DATE_ >= '{bas}'
