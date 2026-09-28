-- M52 Tedarikçi carilerinde özel kod (SPECODE) dağılımı: matbaa / kağıtçı özel kodunun Logo'daki yazımı
-- buradan seçilir (kural uydurulmaz). Ayar: SUPPLY_PRINTER_SPECODES, SUPPLY_PAPER_SPECODES.
SELECT C.SPECODE AS ozel_kod, COUNT(*) AS cari
FROM dbo.LG_{firma}_CLCARD C
WHERE C.CODE LIKE '{on_ek}%'
GROUP BY C.SPECODE
