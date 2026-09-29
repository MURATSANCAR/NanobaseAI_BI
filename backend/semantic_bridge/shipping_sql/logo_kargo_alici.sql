-- M44 Kargo maliyeti: pazar yeri eşlemesi. Yılın kargo gideri faturalarını kesen tedarikçilerin vergi kimliği (vergi no,
-- boşsa T.C. kimlik no; 10–11 rakam, hepsi aynı rakam olan yer tutucu değer hariç) ile aynı vergi kimliğine sahip alıcı
-- carilere kestiğimiz taşıyıcı kodlu satış irsaliyeleri (TRCODE 7, 8; iptal hariç), alıcı × taşıyıcı kodu. Yalnız bu
-- eşleşen alıcılar okunur (bize kargo faturası da kesen müşteri = pazar yeri); diğer alıcılar sorguya girmez.
WITH tedarikci AS (
  SELECT DISTINCT X.vergi
  FROM (
    SELECT COALESCE(NULLIF(LTRIM(RTRIM(T.TAXNR)), ''), NULLIF(LTRIM(RTRIM(T.TCKNO)), '')) AS vergi
    FROM dbo.LG_{f}_01_INVOICE I
    JOIN dbo.LG_{f}_01_STLINE L ON L.INVOICEREF = I.LOGICALREF
    JOIN dbo.LG_{f}_SRVCARD V ON V.LOGICALREF = L.STOCKREF
    JOIN dbo.LG_{f}_CLCARD T ON T.LOGICALREF = I.CLIENTREF
    WHERE I.CANCELLED = 0 AND I.TRCODE = 4 AND L.CANCELLED = 0 AND L.LINETYPE = 4
      AND I.DATE_ >= '{bas}' AND I.DATE_ < '{bit}' AND V.CODE IN ({hizmetler})
  ) X
  WHERE LEN(X.vergi) IN (10, 11) AND X.vergi NOT LIKE '%[^0-9]%' AND REPLACE(X.vergi, LEFT(X.vergi, 1), '') <> ''
),
alici AS (
  SELECT C.CODE AS cari, C.DEFINITION_ AS unvan,
    COALESCE(NULLIF(LTRIM(RTRIM(C.TAXNR)), ''), NULLIF(LTRIM(RTRIM(C.TCKNO)), '')) AS vergi, F.SHPAGNCOD AS kod
  FROM dbo.LG_{f}_01_STFICHE F
  JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = F.CLIENTREF
  WHERE F.CANCELLED = 0 AND F.TRCODE IN (7,8) AND F.DATE_ >= '{bas}' AND F.DATE_ < '{bit}'
    AND LTRIM(RTRIM(ISNULL(F.SHPAGNCOD, ''))) <> ''
)
SELECT A.cari, A.unvan, A.vergi, A.kod, COUNT(*) AS irsaliye
FROM alici A
JOIN tedarikci T ON T.vergi = A.vergi
GROUP BY A.cari, A.unvan, A.vergi, A.kod
