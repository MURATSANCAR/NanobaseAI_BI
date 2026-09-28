-- M52 Tedarikçi carileri ve bu yılın bakiyesi (Logo, yalnız okuma).
-- Tedarikçi: cari kodu {on_ek} ile başlayan (satıcılar, 320). Bakiye = alacak − borç (SIGN 1 − SIGN 0), iptal hariç,
-- yıl başından bu yana; her yıl ayrı Logo firmasıdır ve önceki yıldan devir yıl başındaki satırdır.
-- Aynı tanım: katalog «satici-borcu-vadesi-gecmis-fifo» (B bölümü). Özel kod (SPECODE) matbaa / kağıtçı ayrımı içindir.
SELECT C.LOGICALREF AS ref, C.CODE AS kod, C.DEFINITION_ AS unvan, C.SPECODE AS ozel_kod,
  ISNULL(B.bakiye, 0) AS bakiye
FROM dbo.LG_{firma}_CLCARD C
LEFT JOIN (
  SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN = 1 THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
  FROM dbo.LG_{firma}_{donem}_CLFLINE L
  WHERE L.CANCELLED = 0 AND L.DATE_ >= '{yil_basi}'
  GROUP BY L.CLIENTREF
) B ON B.CLIENTREF = C.LOGICALREF
WHERE C.CODE LIKE '{on_ek}%'
