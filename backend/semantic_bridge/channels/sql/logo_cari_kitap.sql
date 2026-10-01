-- M42 kitap × kanal: kapsamdaki grup (cari ya da kanal kodu) × stok kodu × ay. Alım (kanala satış), iade ve maliyet;
-- kitap × kanal matrisi, kanal detayındaki kitap ve iade listeleri ve M9 birim maliyetiyle marj tamamlama bundan hesaplanır.
SELECT {grup} AS grup, I.CODE AS stok_kodu, MONTH(SH.DATE_) AS ay,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE 0 END) AS satis_adet,
  SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.AMOUNT ELSE 0 END) AS iade_adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.VATMATRAH ELSE 0 END) AS satis_ciro,
  SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.VATMATRAH ELSE 0 END) AS iade_ciro,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) AND ISNULL(S.OUTCOST, 0) > 0 THEN S.AMOUNT * S.OUTCOST ELSE 0 END) AS maliyet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) AND ISNULL(S.OUTCOST, 0) > 0 THEN S.VATMATRAH ELSE 0 END) AS maliyetli_ciro,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) AND ISNULL(S.OUTCOST, 0) <= 0 THEN S.AMOUNT ELSE 0 END) AS maliyetsiz_adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) AND ISNULL(S.OUTCOST, 0) <= 0 THEN S.VATMATRAH ELSE 0 END) AS maliyetsiz_ciro
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_01_INVOICE AS SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.LINETYPE = 0 AND S.TRCODE IN (2,3,7,8,9)
  AND SH.DATE_ >= '{year}-01-01' AND SH.DATE_ < '{next}-01-01'
  AND ({scope})
GROUP BY {grup}, I.CODE, MONTH(SH.DATE_)
