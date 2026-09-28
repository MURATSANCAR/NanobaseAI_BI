-- Eşleme listesi: e-ticaret kanal kodlu cariler ve tek tek eşlenmiş cariler (satışı olmasa da listelenir).
SELECT C.CODE AS cari_kodu, C.DEFINITION_ AS unvan, C.SPECODE2 AS kanal, C.LOGICALREF AS ref
FROM dbo.LG_{firm}_CLCARD AS C
WHERE ({scope})
