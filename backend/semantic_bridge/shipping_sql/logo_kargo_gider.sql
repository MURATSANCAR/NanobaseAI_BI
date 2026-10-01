-- M44 Kargo maliyeti: kargo ve nakliye gideri. Alınan hizmet faturaları (TRCODE 4, iptal hariç), hizmet satırları
-- (LINETYPE 4) hizmet kartına STOCKREF ile bağlanır; hizmet kodları ayardan (SHIPPING_COST_SERVICE_CODES). Satır TOTAL
-- KDV hariçtir. Faturalar toplu kesilir (tek satır, gönderi dökümü yok): bir satır = bir fatura × bir hizmet kodu.
-- Vergi kimliği = cari vergi numarası, boşsa T.C. kimlik numarası; yalnız pazar yeri eşlemesinde kullanılır, ekrana gitmez.
SELECT I.LOGICALREF AS fatura, I.DATE_ AS tarih, C.CODE AS cari, C.DEFINITION_ AS unvan,
  COALESCE(NULLIF(LTRIM(RTRIM(C.TAXNR)), ''), NULLIF(LTRIM(RTRIM(C.TCKNO)), '')) AS vergi,
  V.CODE AS hizmet, V.DEFINITION_ AS hizmet_adi, SUM(L.TOTAL) AS tutar
FROM dbo.LG_{f}_01_INVOICE I
JOIN dbo.LG_{f}_01_STLINE L ON L.INVOICEREF = I.LOGICALREF
JOIN dbo.LG_{f}_SRVCARD V ON V.LOGICALREF = L.STOCKREF
JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = I.CLIENTREF
WHERE I.CANCELLED = 0 AND I.TRCODE = 4 AND L.CANCELLED = 0 AND L.LINETYPE = 4
  AND I.DATE_ >= '{bas}' AND I.DATE_ < '{bit}' AND V.CODE IN ({hizmetler})
GROUP BY I.LOGICALREF, I.DATE_, C.CODE, C.DEFINITION_, C.TAXNR, C.TCKNO, V.CODE, V.DEFINITION_
